"""Fetch raw UN Comtrade data for the us_china_africa_trade pipeline.

Pulls HS 2-digit (cmdCode=AG2), annual, nominal USD, 2000-2025, for the three
reporter-partner setups defined in the data contract:

  reporter_partner/  US (842) and China (156) as reporters, all 54 AU members
                     as partners (one call per reporter x year x flow).
  reporter_world/    US (842) and China (156) as reporters, World (partner 0)
                     total (one call per reporter x year x flow). Needed for
                     the *_World_ex_Africa_total columns (= World - Africa) in
                     25_totals; the AU-partner pull above does not include it.
  africa_reporter/   each of the 54 AU members as reporter, ALL partners
                     (one call per country x year x flow; partners aggregated
                     to 8 regions downstream).

Both `imports` (flowCode M) and `exports` (flowCode X) are fetched separately;
`two_way` is derived later, never fetched.

Classification: clCode "HS" returns each year's data in the revision the
reporter originally filed (`classificationCode` in each row, e.g. H5/H6). This
gives the native-revision pull the design calls for and maximises coverage —
see context/09_hs_revision_map.md.

Raw JSON is cached one file per cell under raw_data/ and NEVER overwritten
(cross-cutting rule 1). Re-running skips any cell already cached, so the run is
fully resumable across days — important given Comtrade's per-day call limits.

Environment: run with the project's conda env `us_china_africa_trade` (the
uv .venv cannot do TLS on this machine; see decision log 2026-06-15).
The API key is read from .env (COMETRADE_API_KEY, with COMETRADE_SECONDARY_KEY
as fallback) and never hard-coded.

Usage examples:
    python scripts/10_fetch_comtrade.py                 # full run, resumable
    python scripts/10_fetch_comtrade.py --setup reporter_partner
    python scripts/10_fetch_comtrade.py --years 2022 2023 --limit 4   # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402
from scripts.logger import logger  # noqa: E402

BASE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
FLOWS = {"imports": "M", "exports": "X"}
REQUEST_PAUSE_S = 0.6  # polite spacing between calls
CALL_TIMEOUT_S = 120


# ---------------------------------------------------------------------------
# .env (hand-parsed; never written to)
# ---------------------------------------------------------------------------
def load_api_keys() -> list[str]:
    env_path = config.Paths.project / ".env"
    if not env_path.exists():
        raise SystemExit(f"Missing {env_path}. Expected COMETRADE_API_KEY=...")
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    keys = [env[k] for k in ("COMETRADE_API_KEY", "COMETRADE_SECONDARY_KEY") if env.get(k)]
    if not keys:
        raise SystemExit("No COMETRADE_API_KEY found in .env")
    return keys


# ---------------------------------------------------------------------------
# HTTP session: OS trust store (corporate proxy CA) + retry/backoff
# ---------------------------------------------------------------------------
class _OSStoreAdapter(HTTPAdapter):
    """Verify TLS against the Windows system trust store rather than certifi's
    bundle, so the corporate proxy CA is trusted."""

    def init_poolmanager(self, *a, **kw):
        ctx = create_urllib3_context()
        ctx.load_default_certs()
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, *a, **kw):
        ctx = create_urllib3_context()
        ctx.load_default_certs()
        kw["ssl_context"] = ctx
        return super().proxy_manager_for(*a, **kw)


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1.5,  # 0, 1.5, 3, 6, 12s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    adapter = _OSStoreAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("https://", adapter)
    return s


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def cell_path(setup: str, label: str, year: int, flow: str) -> Path:
    return config.Paths.raw_data / setup / f"{label}_{year}_{flow}.json"


def already_cached(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def save_cell(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic; partial writes never look "cached"


# ---------------------------------------------------------------------------
# Fetch one cell
# ---------------------------------------------------------------------------
def fetch_cell(session, keys, *, reporter_code, partner_codes, year, flow_code):
    """Return the parsed JSON body for one (reporter, partners, year, flow) cell.

    partner_codes: comma-joined string, or None to request all partners.
    Raises on non-200 after retries; caller decides how to record the failure.
    """
    params = {
        "reporterCode": reporter_code,
        "period": str(year),
        "flowCode": flow_code,
        "cmdCode": "AG2",
    }
    if partner_codes is not None:
        params["partnerCode"] = partner_codes

    last_exc = None
    for key in keys:  # fall back to secondary key on auth/limit failure
        try:
            r = session.get(
                BASE_URL,
                params=params,
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=CALL_TIMEOUT_S,
            )
            if r.status_code in (401, 403, 429):
                last_exc = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                continue  # try next key
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last_exc = e
            continue
    raise last_exc if last_exc else RuntimeError("fetch failed")


# ---------------------------------------------------------------------------
# Setups
# ---------------------------------------------------------------------------
def iter_jobs(setups, years, flows):
    """Yield (setup, label, reporter_code, partner_codes, year, flow_name, flow_code)."""
    au_codes = list(config.AFRICA_AU_COUNTRIES.keys())
    au_partner_str = ",".join(au_codes)

    if "reporter_partner" in setups:
        for name, code in config.REPORTERS.items():  # US, China
            for year in years:
                for flow_name, flow_code in flows.items():
                    yield ("reporter_partner", name, code, au_partner_str, year, flow_name, flow_code)

    if "reporter_world" in setups:
        for name, code in config.REPORTERS.items():  # US, China vs World (0)
            for year in years:
                for flow_name, flow_code in flows.items():
                    yield ("reporter_world", name, code, "0", year, flow_name, flow_code)

    if "africa_reporter" in setups:
        for code, meta in config.AFRICA_AU_COUNTRIES.items():
            for year in years:
                for flow_name, flow_code in flows.items():
                    # partner_codes=None -> all partners (aggregated to regions later)
                    yield ("africa_reporter", meta["iso3"], code, None, year, flow_name, flow_code)


def run(setups, years, flows, limit):
    keys = load_api_keys()
    session = build_session()
    logger.info("Fetching setups=%s years=%d-%d flows=%s (keys available: %d)",
                ",".join(setups), min(years), max(years), ",".join(flows), len(keys))

    n_fetched = n_skipped = n_failed = n_done = 0
    revisions: dict[str, int] = {}

    for job in iter_jobs(setups, years, flows):
        setup, label, reporter_code, partner_codes, year, flow_name, flow_code = job
        path = cell_path(setup, label, year, flow_name)

        if already_cached(path):
            n_skipped += 1
            continue

        try:
            body = fetch_cell(session, keys, reporter_code=reporter_code,
                              partner_codes=partner_codes, year=year, flow_code=flow_code)
        except Exception as e:  # noqa: BLE001 - record and continue; rerun resumes
            n_failed += 1
            logger.warning("FAIL %s/%s %d %s: %s", setup, label, year, flow_name, e)
            continue

        data = body.get("data") or []
        save_cell(path, body)
        n_fetched += 1
        for row in data:
            cc = row.get("classificationCode")
            if cc:
                revisions[cc] = revisions.get(cc, 0) + 1
        logger.info("OK   %s/%s %d %s -> %d rows", setup, label, year, flow_name, len(data))

        time.sleep(REQUEST_PAUSE_S)
        n_done += 1
        if limit and n_done >= limit:
            logger.info("Reached --limit=%d; stopping early.", limit)
            break

    logger.info("Done. fetched=%d skipped=%d failed=%d", n_fetched, n_skipped, n_failed)
    if revisions:
        logger.info("HS revisions seen (row counts): %s",
                    ", ".join(f"{k}={v}" for k, v in sorted(revisions.items())))
    if n_failed:
        logger.warning("%d cells failed (likely rate limit). Re-run to resume — cached cells are skipped.", n_failed)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Fetch raw Comtrade data (resumable).")
    p.add_argument("--setup", choices=["reporter_partner", "reporter_world", "africa_reporter"],
                   action="append", help="Limit to one setup (repeatable). Default: all three.")
    p.add_argument("--years", type=int, nargs="+", help="Specific years. Default: 2000-2025.")
    p.add_argument("--flows", choices=list(FLOWS), nargs="+", help="Default: imports exports.")
    p.add_argument("--limit", type=int, default=0, help="Stop after N successful fetches (smoke test).")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    setups = a.setup or ["reporter_partner", "reporter_world", "africa_reporter"]
    years = a.years or config.YEAR_RANGE
    flows = {k: FLOWS[k] for k in (a.flows or list(FLOWS))}
    run(setups, years, flows, a.limit)


if __name__ == "__main__":
    main()
