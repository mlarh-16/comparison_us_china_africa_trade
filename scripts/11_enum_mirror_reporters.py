"""Enumerate the external Comtrade reporters for the partner-mirror pull.

The Comtrade-mirror africa_reporter build (48_africa_reporter_comtrade.py) needs
every non-African country as a REPORTER, pulled against the 54 AU members as
partners. This script derives that reporter universe = the 7 non-Intra_Africa
regions of config.AFRICA_REPORTER_PARTNER_REGIONS, intersected with Comtrade's
valid-reporter reference (drops NES aggregates / defunct codes that cannot
report, e.g. "Other Asia, nes", "Oceania, nes").

Writes raw_data/mirror_reporters.json:
  {reporter_region: {code: region}, names: {code: text}, generated_from: url}

10_fetch_comtrade.py (setup 'partner_mirror') and 48_africa_reporter_comtrade.py
both read that file. US (842) and China (156) are NOT included here — they are
already cached under reporter_partner/ and mapped to regions USA/China directly.

Run: conda run -n us_china_africa_trade python scripts/11_enum_mirror_reporters.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

# reuse the fetcher's TLS session (OS trust store) for the reference call
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "fetch10", Path(__file__).resolve().parent / "10_fetch_comtrade.py")
_fetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fetch)

REF_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
OUT = config.Paths.raw_data / "mirror_reporters.json"


def valid_reporter_codes() -> dict[str, str]:
    session = _fetch.build_session()
    r = session.get(REF_URL, timeout=60)
    r.raise_for_status()
    rows = r.json()
    rows = rows.get("results") or rows.get("data") or rows
    out: dict[str, str] = {}
    for row in rows:
        code = str(row.get("id") or row.get("reporterCode") or "").strip()
        if not code:
            continue
        code = code.zfill(3) if code.isdigit() else code
        out[code] = row.get("text") or row.get("reporterDesc") or ""
    return out


def main() -> None:
    valid = valid_reporter_codes()
    regions = config.AFRICA_REPORTER_PARTNER_REGIONS
    reporter_region: dict[str, str] = {}
    names: dict[str, str] = {}
    for region, codes in regions.items():
        if region == "Intra_Africa":
            continue  # excluded by design (needs African reporters; extra-Africa table)
        if region in ("USA", "China"):
            continue  # already cached under reporter_partner/
        for c in codes:
            if c in valid:
                reporter_region[c] = region
                names[c] = valid[c]
    payload = {"generated_from": REF_URL, "reporter_region": reporter_region, "names": names}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    by_region: dict[str, int] = {}
    for reg in reporter_region.values():
        by_region[reg] = by_region.get(reg, 0) + 1
    n = len(reporter_region)
    calls = n * len(config.YEAR_RANGE) * 2
    print(f"valid Comtrade reporters in reference: {len(valid)}")
    for reg, k in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  {reg:18s} {k}")
    print(f"external reporters: {n}  ->  {n} x {len(config.YEAR_RANGE)} yrs x 2 flows "
          f"= {calls} calls (resumable)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
