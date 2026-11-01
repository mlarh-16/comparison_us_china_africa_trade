"""Build the Africa-as-reporter outputs from the reconciled BACI slice.

Supersedes 44_preliminary_africa_reporter.py (direct Comtrade import reports),
which over-stated trade with hubs like the US by ~2x on a country-of-origin
basis and failed its US mirror cross-check (05_validation_log.md, 2026-07-31).

Runs in the `us_china_africa_trade` conda env (needs config + country_converter).
Reads raw_data/baci/baci_africa_slice.csv (produced by 12_fetch_baci.py in the
canada .venv), maps partner ISO3 -> 8 world regions (same partition logic as
config, ISO3-keyed) + an explicit residual line, maps HS2 -> main 4-category,
aggregates across AU members, derives two_way, and writes long + wide CSVs.

BACI is reconciled bilateral trade => source = 'baci_reconciled' (no direct/
mirror/mixed). BACI has no HS chapter 99 => classified HS 01-97 only, no
'unspecified' line. Coverage: 2000-2024 (BACI current release).

Run: conda run -n us_china_africa_trade python scripts/44_africa_reporter.py
"""
from __future__ import annotations

import os

import pandas as pd

from config import AFRICA_AU_COUNTRIES, HS_CATEGORY_MAP_MAIN, Paths

BACI_DIR = Paths.raw_data / "baci"
SLICE = BACI_DIR / "baci_africa_slice.csv"
COVERAGE = BACI_DIR / "baci_coverage.csv"

LONG = Paths.output / "us_china_africa_trade_africa_reporter_long.csv"
WIDE = Paths.output / "us_china_africa_trade_africa_reporter_wide.csv"
TOTALS = Paths.output / "us_china_africa_trade_africa_reporter_totals_long.csv"
TOTALS_WIDE = Paths.output / "us_china_africa_trade_africa_reporter_totals_wide.csv"
TOTALS_WIDE_PCT = Paths.output / "us_china_africa_trade_africa_reporter_totals_wide_pct.csv"
TOTALS_WIDE_PCT_EXTRA = Paths.output / "us_china_africa_trade_africa_reporter_totals_wide_pct_extra_africa.csv"

# Superseded PRELIMINARY outputs to remove once the real files are written.
PRELIMINARY = [
    "us_china_africa_trade_africa_reporter_PRELIMINARY.csv",
    "us_china_africa_trade_africa_reporter_PRELIMINARY_regions_share.csv",
    "us_china_africa_trade_africa_reporter_PRELIMINARY_regions_usd.csv",
]

RESIDUAL_LABEL = "Other_residual (nes)"
REGION_ORDER = ["USA", "China", "N_America_ex_US", "S_America",
                "Asia_ex_China", "Europe", "Oceania", "Intra_Africa", RESIDUAL_LABEL]
# Column order for the wide totals: the four focus regions first, then the rest.
TOTALS_WIDE_REGION_ORDER = (["USA", "China", "Europe", "Asia_ex_China"]
                            + [r for r in REGION_ORDER
                               if r not in {"USA", "China", "Europe", "Asia_ex_China"}])
FLOW_ORDER = ["imports", "exports", "two_way"]
CATEGORY_ORDER = list(HS_CATEGORY_MAP_MAIN.keys())

# BACI ISO3 tokens absent from coco but that ARE placeable, mapped to match
# config's Comtrade treatment (see config._EXTRA_COMTRADE_PARTNER_CODES). The
# BACI iso3 token is shown with its numeric country_code (baci_country_codes.csv):
#   S19 = code 490 "Other Asia, nes" (Taiwan)      -> Asia_ex_China
#   ANT = code 530 Netherlands Antilles            -> S_America
#   SCG = code 891 Serbia & Montenegro             -> Europe
# Code 849 "US Misc. Pacific Isds" (BACI token PUS) stays residual per
# config.RESIDUAL_PARTNER_CODES ("849").
ISO3_REGION_OVERRIDES = {"S19": "Asia_ex_China", "ANT": "S_America", "SCG": "Europe"}


def build_iso3_region_map(all_iso3: set[str]) -> dict[str, str]:
    """ISO3 -> one of 8 regions, mirroring config._build_partner_regions but keyed
    by ISO3. USA/China singletons; Americas split Northern vs rest; continents
    1:1; Africa -> Intra_Africa. Codes coco cannot place are left unmapped and
    routed to the residual line by the caller."""
    import country_converter as coco

    d = coco.CountryConverter().data
    cont = dict(zip(d["ISO3"], d["continent"]))
    unregion = dict(zip(d["ISO3"], d["UNregion"]))

    mapping: dict[str, str] = {}
    for iso in all_iso3:
        if iso == "USA":
            mapping[iso] = "USA"
        elif iso == "CHN":
            mapping[iso] = "China"
        elif iso in ISO3_REGION_OVERRIDES:
            mapping[iso] = ISO3_REGION_OVERRIDES[iso]
        else:
            continent = cont.get(iso)
            if continent is None or isinstance(continent, float):
                continue  # unmapped -> residual
            if continent == "America":
                mapping[iso] = ("N_America_ex_US"
                                if unregion.get(iso) == "Northern America" else "S_America")
            elif continent == "Asia":
                mapping[iso] = "Asia_ex_China"
            elif continent in ("Europe", "Oceania"):
                mapping[iso] = continent
            elif continent == "Africa":
                mapping[iso] = "Intra_Africa"
    return mapping


def build_long() -> pd.DataFrame:
    df = pd.read_csv(SLICE, dtype={"hs2": "string", "partner_iso3": "string"})

    # HS2 -> main 4-category
    ch2cat = {ch: cat for cat, chs in HS_CATEGORY_MAP_MAIN.items() for ch in chs}
    df["category"] = df["hs2"].map(ch2cat)
    unmapped_hs = sorted(set(df.loc[df.category.isna(), "hs2"].dropna()))
    if unmapped_hs:
        raise SystemExit(f"Unexpected unmapped HS2 chapters (fix scheme): {unmapped_hs}")

    # partner ISO3 -> region; coco-unplaceable codes -> explicit residual line
    reg_map = build_iso3_region_map(set(df.partner_iso3.dropna().unique()))
    df["partner_region"] = df["partner_iso3"].map(reg_map).fillna(RESIDUAL_LABEL)

    long = (df.groupby(["year", "flow", "partner_region", "category"], observed=True)["value_usd"]
              .sum().reset_index())

    # two_way = imports + exports
    two_way = (long.groupby(["year", "partner_region", "category"], observed=True)["value_usd"]
                   .sum().reset_index())
    two_way["flow"] = "two_way"
    long = pd.concat([long, two_way[long.columns]], ignore_index=True)

    long["source"] = "baci_reconciled"
    long = long.rename(columns={"year": "Year"})
    long["partner_region"] = pd.Categorical(long.partner_region, REGION_ORDER, ordered=True)
    long["flow"] = pd.Categorical(long.flow, FLOW_ORDER, ordered=True)
    long["category"] = pd.Categorical(long.category, CATEGORY_ORDER, ordered=True)
    long = long.sort_values(["flow", "Year", "partner_region", "category"]).reset_index(drop=True)
    return long[["Year", "flow", "partner_region", "category", "value_usd", "source"]]


def build_totals(long: pd.DataFrame) -> pd.DataFrame:
    """Region totals across all 4 categories: (Year, flow, partner_region) -> value_usd.
    e.g. one number for Europe 2013 imports/exports/two_way."""
    tot = (long.groupby(["Year", "flow", "partner_region"], observed=True)["value_usd"]
               .sum().reset_index())
    tot["source"] = "baci_reconciled"
    tot["partner_region"] = pd.Categorical(tot.partner_region, REGION_ORDER, ordered=True)
    tot["flow"] = pd.Categorical(tot.flow, FLOW_ORDER, ordered=True)
    return tot.sort_values(["flow", "Year", "partner_region"]).reset_index(drop=True)


def build_totals_wide(totals: pd.DataFrame) -> pd.DataFrame:
    """(Year, flow) rows x one column per region. Regions ordered with the four
    focus regions (USA, China, Europe, Asia_ex_China) first."""
    wide = (totals.pivot_table(index=["Year", "flow"], columns="partner_region",
                               values="value_usd", observed=True)
                  .reset_index())
    wide.columns.name = None
    region_cols = [r for r in TOTALS_WIDE_REGION_ORDER if r in wide.columns]
    wide = wide[["Year", "flow"] + region_cols]
    wide["flow"] = pd.Categorical(wide.flow, FLOW_ORDER, ordered=True)
    return wide.sort_values(["Year", "flow"]).reset_index(drop=True)


def build_totals_wide_pct(wide: pd.DataFrame) -> pd.DataFrame:
    """Same layout as the wide totals, but each region as a % of that row's total
    (Africa's total trade for the Year+flow). Region columns sum to 100 per row."""
    region_cols = [c for c in wide.columns if c not in ("Year", "flow")]
    pct = wide.copy()
    row_total = pct[region_cols].sum(axis=1)  # NaN (absent residual) treated as 0
    pct[region_cols] = pct[region_cols].div(row_total, axis=0).mul(100).round(2)
    return pct


def build_totals_wide_pct_extra_africa(wide: pd.DataFrame) -> pd.DataFrame:
    """Shares of Africa's EXTRA-continental trade: the denominator excludes
    Intra_Africa, so every remaining flow is counted once and the two-way
    intra-Africa double-count cannot distort external partners' shares (an
    intra-African shipment is one AU member's export AND another's import; an
    external flow appears once). Intra_Africa is dropped; the remaining region
    columns sum to 100 per row. This is the publication-safe partner-share view.
    """
    region_cols = [c for c in wide.columns if c not in ("Year", "flow", "Intra_Africa")]
    pct = wide[["Year", "flow"] + region_cols].copy()
    row_total = pct[region_cols].sum(axis=1)  # NaN (absent residual) treated as 0
    pct[region_cols] = pct[region_cols].div(row_total, axis=0).mul(100).round(2)
    return pct


def build_wide(long: pd.DataFrame) -> pd.DataFrame:
    wide = (long.pivot_table(index=["partner_region", "category", "flow"],
                             columns="Year", values="value_usd", observed=True)
                .reset_index())
    wide.columns.name = None
    wide["partner_region"] = pd.Categorical(wide.partner_region, REGION_ORDER, ordered=True)
    wide["flow"] = pd.Categorical(wide.flow, FLOW_ORDER, ordered=True)
    wide["category"] = pd.Categorical(wide.category, CATEGORY_ORDER, ordered=True)
    return wide.sort_values(["partner_region", "category", "flow"]).reset_index(drop=True)


def validate(long: pd.DataFrame) -> None:
    assert (long.value_usd < 0).sum() == 0, "negative values present"
    tw = long[long.flow == "two_way"].set_index(["Year", "partner_region", "category"]).value_usd
    im = long[long.flow == "imports"].set_index(["Year", "partner_region", "category"]).value_usd
    ex = long[long.flow == "exports"].set_index(["Year", "partner_region", "category"]).value_usd
    delta = (tw - im.reindex(tw.index).fillna(0) - ex.reindex(tw.index).fillna(0)).abs()
    assert delta.max() < 1.0, f"two_way != imports+exports (max {delta.max():.2f})"
    print(f"validation OK: {len(long)} rows, 0 negatives, two_way reconciles")


def main() -> None:
    long = build_long()
    validate(long)
    long.to_csv(LONG, index=False, encoding="utf-8")

    totals = build_totals(long)
    totals.to_csv(TOTALS, index=False, encoding="utf-8")
    totals_wide = build_totals_wide(totals)
    totals_wide.to_csv(TOTALS_WIDE, index=False, encoding="utf-8")
    build_totals_wide_pct(totals_wide).to_csv(TOTALS_WIDE_PCT, index=False, encoding="utf-8")
    build_totals_wide_pct_extra_africa(totals_wide).to_csv(TOTALS_WIDE_PCT_EXTRA, index=False, encoding="utf-8")

    wide = build_wide(long)
    wide.to_csv(WIDE, index=False, encoding="utf-8")

    # coverage footer appended below a blank line (not part of the data grain)
    if COVERAGE.exists():
        cov = pd.read_csv(COVERAGE)
        with open(WIDE, "a", encoding="utf-8", newline="") as f:
            f.write("\n")
            f.write("coverage: distinct AU members present in BACI per year\n")
            cov.to_csv(f, index=False)

    # remove the superseded PRELIMINARY outputs
    removed = []
    for name in PRELIMINARY:
        p = Paths.output / name
        if p.exists():
            p.unlink()
            removed.append(name)

    print(f"wrote {LONG.name} ({len(long)} rows), {TOTALS.name} ({len(totals)} rows), "
          f"{TOTALS_WIDE.name}, {TOTALS_WIDE_PCT.name}, {TOTALS_WIDE_PCT_EXTRA.name}, "
          f"{WIDE.name} ({len(wide)} rows)")
    if removed:
        print("removed superseded PRELIMINARY files:", ", ".join(removed))


if __name__ == "__main__":
    main()
