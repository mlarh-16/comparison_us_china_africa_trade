"""PRELIMINARY Africa-as-reporter regional breakdown (side deliverable).

NOTE: PRELIMINARY and PARTIAL. Built only from AU reporters with a COMPLETE
cache (all 26 years x 2 flows). The `africa_reporter` fetch is unfinished and
the completed countries skew North/West Africa — the biggest traders (South
Africa, Angola, full Nigeria, Kenya, DR Congo) are NOT in yet. So absolute
shares are NOT representative of all Africa; the TREND is more reliable than
the levels. This is NOT an official contract output and uses no mirror fallback
(direct reports only).

Method: each AU reporter's trade with every partner, mapped to the 8 world
regions via config.AFRICA_REPORTER_PARTNER_REGIONS (Comtrade-legacy codes
patched 2026-06-17, see 08_debug_log.md). Non-geographic / unassignable codes
(config.RESIDUAL_PARTNER_CODES) are reported as a single residual line, never
forced into a region. share_pct is within (Year, flow) so it sums to 100%.

Output: output/us_china_africa_trade_africa_reporter_PRELIMINARY.csv
Run: conda run -n us_china_africa_trade python scripts/44_preliminary_africa_reporter.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import pandas as pd

from config import (
    AFRICA_REPORTER_PARTNER_REGIONS,
    RESIDUAL_PARTNER_CODES,
    Paths,
)

RAW = Paths.raw_data / "africa_reporter"
DEST = Paths.output / "us_china_africa_trade_africa_reporter_PRELIMINARY.csv"
RESIDUAL_LABEL = "Other_residual (nes/bunkers)"

REGION_ORDER = [
    "USA", "China", "Europe", "Asia_ex_China", "Intra_Africa",
    "S_America", "N_America_ex_US", "Oceania", RESIDUAL_LABEL,
]


def _code_to_region() -> dict[str, str]:
    m = {}
    for region, codes in AFRICA_REPORTER_PARTNER_REGIONS.items():
        for c in codes:
            m[str(int(c))] = region
    for c in RESIDUAL_PARTNER_CODES:
        m[str(int(c))] = RESIDUAL_LABEL
    return m


def complete_reporters() -> set[str]:
    cells: dict[str, set] = defaultdict(set)
    for f in RAW.glob("*.json"):
        m = re.match(r"(.+)_(\d{4})_(imports|exports)$", f.stem)
        if m:
            cells[m.group(1)].add((int(m.group(2)), m.group(3)))
    return {c for c, v in cells.items() if len(v) == 52}


def main() -> None:
    code2region = _code_to_region()
    panel = complete_reporters()

    # (year, flow, region) -> value
    acc: dict[tuple, float] = defaultdict(float)
    unmapped: dict[str, float] = defaultdict(float)
    for f in RAW.glob("*.json"):
        m = re.match(r"(.+)_(\d{4})_(imports|exports)$", f.stem)
        if not m or m.group(1) not in panel:
            continue
        year, flow = int(m.group(2)), m.group(3)
        for row in json.loads(f.read_text(encoding="utf-8")).get("data") or []:
            if row.get("partner2Code", 0) not in (0, None):
                continue
            val = row.get("primaryValue")
            pc = row.get("partnerCode")
            if val is None or pc == 0:  # skip the World(0) total line
                continue
            region = code2region.get(str(int(pc)))
            if region is None:
                unmapped[str(int(pc))] += float(val)
                continue
            acc[(year, flow, region)] += float(val)

    if unmapped:
        raise SystemExit(f"Unexpected unmapped codes (fix config): {dict(unmapped)}")

    df = pd.DataFrame(
        [{"Year": y, "flow": fl, "partner_region": r, "value_usd": v}
         for (y, fl, r), v in acc.items()]
    )

    # Derive two_way = imports + exports.
    tw = (df[df.flow.isin(["imports", "exports"])]
          .groupby(["Year", "partner_region"], as_index=False)["value_usd"].sum())
    tw["flow"] = "two_way"
    df = pd.concat([df, tw[df.columns]], ignore_index=True)

    # share within (Year, flow)
    df["share_pct"] = (df.groupby(["Year", "flow"])["value_usd"]
                       .transform(lambda s: s / s.sum() * 100)).round(2)
    df["n_reporters"] = len(panel)

    df["partner_region"] = pd.Categorical(df.partner_region, REGION_ORDER, ordered=True)
    flow_order = pd.CategoricalDtype(["imports", "exports", "two_way"], ordered=True)
    df["flow"] = df["flow"].astype(flow_order)
    df = df.sort_values(["flow", "Year", "partner_region"]).reset_index(drop=True)

    df.to_csv(DEST, index=False, encoding="utf-8")
    print(f"{DEST.name}: {len(df)} rows | panel = {len(panel)} complete AU reporters")
    print("panel:", ", ".join(sorted(panel)))


if __name__ == "__main__":
    main()
