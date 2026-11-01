"""Africa-as-reporter partner shares, rebuilt from COMTRADE mirror data.

Single-source alternative to the BACI build (44_africa_reporter.py). Instead of
asking African countries what they traded (direct reports are origin-biased and
sparsely reported), it asks each PARTNER what it traded with the 54 AU members
and flips the direction:

    partner's EXPORTS to AU  ==  Africa's IMPORTS from that partner region
    partner's IMPORTS from AU ==  Africa's EXPORTS to that partner region

Reporters come from two caches, both written by 10_fetch_comtrade.py:
  reporter_partner/  US (842) and China (156)          -> regions USA, China
  partner_mirror/    the 171 external reporter countries -> the other 5 regions
                     (enumerated in raw_data/mirror_reporters.json)

Intra-Africa is deliberately EXCLUDED: it would need African reporters (the same
sparse-coverage set that sank the direct build), and the publication headline is
the EXTRA-continental share, where intra-Africa is not in the denominator. So
this build targets the extra-Africa share table only.

This is RAW mirror data: no CIF/FOB harmonisation and no importer/exporter
reconciliation (that is exactly what BACI does). Expect region cells to sit
~5-15% off BACI. source = 'comtrade_mirror_raw'. Classified HS 01-97 only
(chapter 99 dropped, matching BACI so the two are comparable).

Run: conda run -n us_china_africa_trade python scripts/48_africa_reporter_comtrade.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

RAW = config.Paths.raw_data
OUT = config.Paths.output
MIRROR_MAP = RAW / "mirror_reporters.json"

# reporter flowCode label -> Africa's flow (the mirror flip)
FLOW_FLIP = {"exports": "imports", "imports": "exports"}
FLOW_ORDER = ["imports", "exports", "two_way"]

# extra-Africa regions only (no Intra_Africa, no residual): focus regions first
REGION_ORDER = ["USA", "China", "Europe", "Asia_ex_China",
                "N_America_ex_US", "S_America", "Oceania"]
CATEGORY_ORDER = list(config.HS_CATEGORY_MAP_MAIN.keys())
CH_TO_MAIN = {ch: cat for cat, chs in config.HS_CATEGORY_MAP_MAIN.items() for ch in chs}

LONG = OUT / "us_china_africa_trade_africa_reporter_comtrade_long.csv"
TOTALS_WIDE = OUT / "us_china_africa_trade_africa_reporter_comtrade_totals_wide.csv"
PCT_EXTRA = OUT / "us_china_africa_trade_africa_reporter_comtrade_totals_wide_pct_extra_africa.csv"


def _load_cache(cache_dir: Path, label_to_region: dict[str, str]) -> list[dict]:
    """Read a reporter-vs-AU-partner JSON cache into flipped, categorised records.

    Only cells whose reporter label maps to a wanted region are kept. ch99 and
    partner2Code breakdowns are dropped (matching the aggregate pipeline)."""
    records: list[dict] = []
    if not cache_dir.exists():
        return records
    for f in sorted(cache_dir.glob("*.json")):
        label, year, rep_flow = f.stem.split("_")  # e.g. 276_2022_exports / China_2022_imports
        region = label_to_region.get(label)
        if region is None:
            continue
        africa_flow = FLOW_FLIP[rep_flow]
        body = json.loads(f.read_text(encoding="utf-8"))
        for row in body.get("data") or []:
            # keep only fully-aggregated TOTAL rows. The fetch pins these, but
            # filter defensively so any legacy/unpinned cell can't double-count
            # via mode-of-transport / customs / partner2 breakdowns.
            if row.get("partner2Code", 0) not in (0, None):
                continue
            if str(row.get("motCode", "0")) not in ("0", "None"):
                continue
            if str(row.get("customsCode", "C00")) not in ("C00", "None"):
                continue
            val = row.get("primaryValue")
            if val is None:
                continue
            partner3 = f"{int(row['partnerCode']):03d}"
            if partner3 not in config.AFRICA_AU_COUNTRIES:
                continue  # only AU partners count toward Africa's trade
            cat = CH_TO_MAIN.get(row.get("cmdCode"))
            if cat is None:
                continue  # ch99 / outside 01-97
            records.append({"Year": int(year), "flow": africa_flow,
                            "partner_region": region, "category": cat,
                            "value_usd": float(val)})
    return records


def build_long() -> pd.DataFrame:
    # US / China from the reporter_partner cache
    recs = _load_cache(RAW / "reporter_partner", {"US": "USA", "China": "China"})
    # the 171 external reporters from the partner_mirror cache
    if MIRROR_MAP.exists():
        m = json.loads(MIRROR_MAP.read_text(encoding="utf-8"))
        recs += _load_cache(RAW / "partner_mirror", m["reporter_region"])
    if not recs:
        raise SystemExit("No usable cache found (reporter_partner or partner_mirror).")

    df = pd.DataFrame.from_records(recs)
    long = (df.groupby(["Year", "flow", "partner_region", "category"], observed=True)["value_usd"]
              .sum().reset_index())
    two_way = (long.groupby(["Year", "partner_region", "category"], observed=True)["value_usd"]
                   .sum().reset_index())
    two_way["flow"] = "two_way"
    long = pd.concat([long, two_way[long.columns]], ignore_index=True)
    long["source"] = "comtrade_mirror_raw"

    long["partner_region"] = pd.Categorical(long.partner_region, REGION_ORDER, ordered=True)
    long["flow"] = pd.Categorical(long.flow, FLOW_ORDER, ordered=True)
    long["category"] = pd.Categorical(long.category, CATEGORY_ORDER, ordered=True)
    return long.sort_values(["flow", "Year", "partner_region", "category"]).reset_index(drop=True)


def build_totals_wide(long: pd.DataFrame) -> pd.DataFrame:
    tot = (long.groupby(["Year", "flow", "partner_region"], observed=True)["value_usd"]
               .sum().reset_index())
    wide = (tot.pivot_table(index=["Year", "flow"], columns="partner_region",
                            values="value_usd", observed=True).reset_index())
    wide.columns.name = None
    cols = [r for r in REGION_ORDER if r in wide.columns]
    wide = wide[["Year", "flow"] + cols]
    wide["flow"] = pd.Categorical(wide.flow, FLOW_ORDER, ordered=True)
    return wide.sort_values(["Year", "flow"]).reset_index(drop=True)


def build_pct_extra(wide: pd.DataFrame) -> pd.DataFrame:
    """Each region as a % of Africa's extra-continental trade (all regions here
    are external, so columns simply sum to 100 per row)."""
    cols = [c for c in wide.columns if c not in ("Year", "flow")]
    pct = wide.copy()
    pct[cols] = pct[cols].div(pct[cols].sum(axis=1), axis=0).mul(100).round(2)
    return pct


def coverage_report(long: pd.DataFrame) -> None:
    present = sorted(long.partner_region.dropna().unique(),
                     key=lambda r: REGION_ORDER.index(r))
    missing = [r for r in REGION_ORDER if r not in present]
    print(f"regions present: {present}")
    if missing:
        print(f"regions MISSING (cache not yet pulled): {missing}")
    yrs = sorted(long.Year.unique())
    print(f"years: {min(yrs)}-{max(yrs)} ({len(yrs)})")


def main() -> None:
    long = build_long()
    coverage_report(long)
    assert (long.value_usd < 0).sum() == 0, "negative values present"
    long.to_csv(LONG, index=False, encoding="utf-8")
    wide = build_totals_wide(long)
    wide.to_csv(TOTALS_WIDE, index=False, encoding="utf-8")
    build_pct_extra(wide).to_csv(PCT_EXTRA, index=False, encoding="utf-8")
    print(f"wrote {LONG.name} ({len(long)} rows), {TOTALS_WIDE.name}, {PCT_EXTRA.name}")


if __name__ == "__main__":
    main()
