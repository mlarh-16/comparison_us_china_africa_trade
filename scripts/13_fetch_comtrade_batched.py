"""Batched partner_mirror fetch — collapses the ~8,788-call one-cell-at-a-time
pull to ~52 calls by requesting ALL reporters at once, one (year, flow) per call.

Comtrade limits found empirically (2026-09-01):
  - up to 12 periods per call  -> so we do ONE year per call
  - many reporterCodes per call -> all 169 external reporters fit in one call
  - ~100k rows per response     -> all-169 x 1 year x 1 flow ~= 67k rows (safe);
                                   a 2nd year or both flows would exceed it
So the plan: for each year x flow, one call for all still-uncached reporters.
If a response ever comes back near the row cap, the reporter set is split in
half and retried (recursive), so no data is silently truncated.

Writes the SAME per-reporter cell files as 10_fetch_comtrade.py
(raw_data/partner_mirror/{code}_{year}_{flow}.json), so resume, the immutability
rule (never overwrite an existing cell), and 48_africa_reporter_comtrade.py all
work unchanged. Reporters absent from a response get an explicit empty cell so
they are marked done (not re-pulled).

No pandas import (keeps it immune to the numpy DLL block seen on this machine).
Reporter universe from raw_data/mirror_reporters.json (11_enum_mirror_reporters.py).

Run: conda run -n us_china_africa_trade python scripts/13_fetch_comtrade_batched.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

PROJ = Path(__file__).resolve().parent.parent
RAW = PROJ / "raw_data"
MIRROR_DIR = RAW / "partner_mirror"
MIRROR_MAP = RAW / "mirror_reporters.json"
URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"

YEARS = list(range(2000, 2026))
FLOWS = {"imports": "M", "exports": "X"}
ROW_CAP = 95_000          # split reporters if a response reaches this (100k API cap)
REQUEST_PAUSE_S = 0.6

# 54 AU member Comtrade codes (source of truth: config.AFRICA_AU_COUNTRIES;
# inlined here to avoid importing config -> country_converter -> pandas).
AU = ("012,818,434,504,729,788,204,854,132,384,270,288,324,624,430,466,478,562,"
      "566,686,694,768,120,140,148,178,180,226,266,678,108,174,262,232,231,404,"
      "450,454,480,508,646,690,706,728,834,800,894,716,024,072,748,426,516,710")


def load_keys() -> list[str]:
    env = {}
    for line in (PROJ / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    keys = [env[k] for k in ("COMETRADE_API_KEY", "COMETRADE_SECONDARY_KEY") if env.get(k)]
    if not keys:
        raise SystemExit("No COMETRADE_API_KEY in .env")
    return keys


class _OSStoreAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = create_urllib3_context(); ctx.load_default_certs(); kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, *a, **kw):
        ctx = create_urllib3_context(); ctx.load_default_certs(); kw["ssl_context"] = ctx
        return super().proxy_manager_for(*a, **kw)


def build_session() -> requests.Session:
    retry = Retry(total=5, backoff_factor=1.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True)
    s = requests.Session()
    s.mount("https://", _OSStoreAdapter(max_retries=retry))
    return s


def cell_path(code: str, year: int, flow: str) -> Path:
    return MIRROR_DIR / f"{code}_{year}_{flow}.json"


def already_cached(code: str, year: int, flow: str) -> bool:
    p = cell_path(code, year, flow)
    return p.exists() and p.stat().st_size > 0


def save_cell(code: str, year: int, flow: str, rows: list) -> None:
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    p = cell_path(code, year, flow)
    if p.exists():  # never overwrite an existing cell (immutability rule)
        return
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"count": len(rows), "data": rows}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)


def fetch_batch(session, keys, reporters: list[str], year: int, flow_code: str):
    """One call: given reporters, one year, one flow. Returns (rows, count) or
    raises. Caller handles the row-cap split."""
    params = {"reporterCode": ",".join(reporters), "period": str(year),
              "flowCode": flow_code, "cmdCode": "AG2", "partnerCode": AU,
              "partner2Code": "0", "motCode": "0", "customsCode": "C00"}
    last = None
    for key in keys:
        try:
            r = session.get(URL, params=params,
                            headers={"Ocp-Apim-Subscription-Key": key}, timeout=300)
        except requests.RequestException as e:
            last = e; continue
        if r.status_code in (401, 403, 429):
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}"); continue
        r.raise_for_status()
        b = r.json()
        return (b.get("data") or []), (b.get("count") or 0)
    raise last if last else RuntimeError("fetch failed")


def do_group(session, keys, reporters, year, flow_name, flow_code, stats):
    """Fetch one (year, flow) for a reporter group, splitting on the row cap."""
    rows, count = fetch_batch(session, keys, reporters, year, flow_code)
    stats["calls"] += 1
    if count >= ROW_CAP and len(reporters) > 1:
        # too close to the 100k cap -> split the reporter set and recurse
        mid = len(reporters) // 2
        print(f"  {year} {flow_name}: {count} rows near cap, splitting {len(reporters)}"
              f" reporters -> {mid}+{len(reporters)-mid}")
        time.sleep(REQUEST_PAUSE_S)
        do_group(session, keys, reporters[:mid], year, flow_name, flow_code, stats)
        time.sleep(REQUEST_PAUSE_S)
        do_group(session, keys, reporters[mid:], year, flow_name, flow_code, stats)
        return
    # group rows by reporter, write a cell per reporter (empty if none)
    by_rep: dict[str, list] = {c: [] for c in reporters}
    for row in rows:
        rc = f"{int(row['reporterCode']):03d}" if str(row.get('reporterCode')).isdigit() else str(row.get('reporterCode'))
        if rc in by_rep:
            by_rep[rc].append(row)
    got = sum(1 for c in reporters if by_rep[c])
    for c in reporters:
        save_cell(c, year, flow_name, by_rep[c])
    stats["cells"] += len(reporters)
    stats["with_data"] += got
    print(f"  {year} {flow_name}: {count} rows, {got}/{len(reporters)} reporters with data")


def main() -> None:
    keys = load_keys()
    session = build_session()
    mm = json.loads(MIRROR_MAP.read_text(encoding="utf-8"))
    all_reporters = list(mm["reporter_region"])
    print(f"batched partner_mirror fetch: {len(all_reporters)} reporters x "
          f"{len(YEARS)} yrs x {len(FLOWS)} flows")

    stats = {"calls": 0, "cells": 0, "with_data": 0, "skipped_groups": 0}
    for year in YEARS:
        for flow_name, flow_code in FLOWS.items():
            missing = [c for c in all_reporters if not already_cached(c, year, flow_name)]
            if not missing:
                stats["skipped_groups"] += 1
                continue
            try:
                do_group(session, keys, missing, year, flow_name, flow_code, stats)
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL {year} {flow_name} ({len(missing)} reporters): {e}")
                continue
            time.sleep(REQUEST_PAUSE_S)

    print(f"\nDone. api_calls={stats['calls']} cells_written~={stats['cells']} "
          f"(with_data={stats['with_data']}) year-flow_groups_skipped={stats['skipped_groups']}")
    print("Now rebuild the table: python scripts/48_africa_reporter_comtrade.py")


if __name__ == "__main__":
    main()
