"""Write the final CSVs and the master Excel workbook.

Builds the US/China datasets from the interim tables (20_aggregate.py) and the
totals (25_totals.py):

  output/us_china_africa_trade_aggregate_long.csv      / _wide.csv
  output/us_china_africa_trade_by_country_long.csv     / _wide.csv
  output/us_china_africa_trade_alt_categories_long.csv / _wide.csv
  output/us_china_africa_trade.xlsx                    (sheets above + tidy_all)

The two africa_reporter outputs are written by `44_africa_reporter.py` (from the
BACI slice), not here. This script folds them into the workbook + `tidy_all` IF
they already exist on disk, so run `44_africa_reporter.py` BEFORE this script (or
re-run this after it) to get the africa_reporter sheets. If they are absent the
workbook is still built, just without them.

Per the 2026-06-15 "show both" decision: `unspecified (HS 99)` is a category
column; `{reporter}_Africa_total` is the official total incl. ch99.

Run: conda run -n us_china_africa_trade python scripts/30_build_outputs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402
from scripts.logger import logger  # noqa: E402

INTERIM = config.Paths.project / "interim"
OUT = config.Paths.output
PREFIX = "us_china_africa_trade"

REPORTER_ORDER = ["China", "US"]
FLOW_ORDER = ["imports", "exports", "two_way"]
MAIN_CATS = ["agricultural goods", "minerals & metals", "apparel",
             "other manufactured goods", "unspecified (HS 99)"]
ALT_CATS = ["raw agrifood", "processed agrifood", "energy minerals", "unrefined minerals",
            "refined minerals", "apparel", "other manufactured", "unspecified (HS 99)"]
YEARS = [str(y) for y in config.YEAR_RANGE]


def _flow_cat(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["flow"] = pd.Categorical(df["flow"], FLOW_ORDER, ordered=True)
    return df


# ---------------------------------------------------------------------------
# aggregate / alt: (Year, flow) rows x reporter-category columns
# ---------------------------------------------------------------------------
def reporter_cat_long(df: pd.DataFrame, cats: list[str], totals: pd.DataFrame | None) -> pd.DataFrame:
    piv = df.pivot_table(index=["year", "flow"], columns=["reporter", "category"],
                         values="value_usd", aggfunc="sum")
    ordered = [(rep, cat) for rep in REPORTER_ORDER for cat in cats]
    piv = piv.reindex(columns=pd.MultiIndex.from_tuples(ordered))
    piv.columns = [f"{rep} {cat}" for rep, cat in piv.columns]
    piv = piv.reset_index()

    if totals is not None:
        tt = totals.pivot_table(index=["year", "flow"], columns="reporter",
                                values=["Africa_total", "World_ex_Africa_total"])
        tt.columns = [f"{rep}_{metric}" for metric, rep in tt.columns]
        tcols = [f"{rep}_{m}" for rep in REPORTER_ORDER
                 for m in ("Africa_total", "World_ex_Africa_total")]
        tt = tt.reindex(columns=tcols).reset_index()
        piv = piv.merge(tt, on=["year", "flow"], how="left")

    piv = _flow_cat(piv).sort_values(["year", "flow"]).reset_index(drop=True)
    return piv.rename(columns={"year": "Year"})


def reporter_cat_wide(df: pd.DataFrame, cats: list[str], totals: pd.DataFrame | None) -> pd.DataFrame:
    """series (reporter-category + totals) x year columns, per flow."""
    long = df.copy()
    long["series"] = long["reporter"] + " " + long["category"]
    series_order = [f"{rep} {cat}" for rep in REPORTER_ORDER for cat in cats]

    if totals is not None:
        t = totals.melt(id_vars=["year", "flow", "reporter"],
                        value_vars=["Africa_total", "World_ex_Africa_total"],
                        var_name="metric", value_name="value_usd")
        t["series"] = t["reporter"] + "_" + t["metric"]
        long = pd.concat([long[["year", "flow", "series", "value_usd"]],
                          t[["year", "flow", "series", "value_usd"]]], ignore_index=True)
        series_order += [f"{rep}_{m}" for rep in REPORTER_ORDER
                         for m in ("Africa_total", "World_ex_Africa_total")]

    wide = long.pivot_table(index=["series", "flow"], columns="year", values="value_usd", aggfunc="sum")
    wide = wide.reindex(columns=config.YEAR_RANGE)
    wide.columns = [str(c) for c in wide.columns]
    wide = wide.reset_index()
    wide["series"] = pd.Categorical(wide["series"], series_order, ordered=True)
    wide = _flow_cat(wide).sort_values(["series", "flow"]).reset_index(drop=True)
    return wide


# ---------------------------------------------------------------------------
# by_country
# ---------------------------------------------------------------------------
def by_country_long(df: pd.DataFrame) -> pd.DataFrame:
    df = _flow_cat(df).sort_values(
        ["year", "flow", "reporter", "country_iso3", "category"]).reset_index(drop=True)
    df = df.rename(columns={"year": "Year"})
    return df[["Year", "flow", "reporter", "country_iso3", "country_name", "category", "value_usd"]]


def by_country_wide(df: pd.DataFrame) -> pd.DataFrame:
    wide = df.pivot_table(index=["reporter", "country_iso3", "country_name", "category", "flow"],
                          columns="year", values="value_usd", aggfunc="sum")
    wide = wide.reindex(columns=config.YEAR_RANGE)
    wide.columns = [str(c) for c in wide.columns]
    wide = wide.reset_index()
    wide["flow"] = pd.Categorical(wide["flow"], FLOW_ORDER, ordered=True)
    return wide.sort_values(["reporter", "country_iso3", "category", "flow"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# tidy_all
# ---------------------------------------------------------------------------
def build_tidy_all(agg: pd.DataFrame, byc: pd.DataFrame, alt: pd.DataFrame,
                   totals: pd.DataFrame, ar: pd.DataFrame | None = None) -> pd.DataFrame:
    cols = ["dataset", "category_scheme", "year", "flow", "reporter", "partner",
            "partner_type", "category", "source", "value_usd"]

    a = agg.assign(dataset="aggregate", category_scheme="main_4", partner="Africa",
                   partner_type="aggregate_africa", source="direct")
    # totals as category rows
    t = totals.melt(id_vars=["year", "flow", "reporter"],
                    value_vars=["Africa_total", "World_ex_Africa_total"],
                    var_name="category", value_name="value_usd").dropna(subset=["value_usd"])
    t = t.assign(dataset="aggregate", category_scheme="main_4", partner="Africa",
                 partner_type="aggregate_africa", source="direct")
    b = byc.assign(dataset="by_country", category_scheme="main_4", partner=byc["country_name"],
                   partner_type="au_country", source="direct")
    al = alt.assign(dataset="alt_categories", category_scheme="alt_7", partner="Africa",
                    partner_type="aggregate_africa", source="direct")

    frames = [a[cols], t[cols], b[cols], al[cols]]
    if ar is not None:
        # africa_reporter (BACI): Africa as reporter, partner = world region
        arr = (ar.rename(columns={"Year": "year", "partner_region": "partner"})
                 .assign(dataset="africa_reporter", category_scheme="main_4",
                         reporter="Africa", partner_type="world_region"))
        frames.append(arr[cols])

    out = pd.concat(frames, ignore_index=True)
    out["flow"] = pd.Categorical(out["flow"], FLOW_ORDER, ordered=True)
    return out.sort_values(["dataset", "reporter", "partner", "year", "flow", "category"]).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    agg = pd.read_csv(INTERIM / "aggregate_main_long.csv")
    alt = pd.read_csv(INTERIM / "alt_categories_long.csv")
    byc = pd.read_csv(INTERIM / "by_country_long.csv")
    totals = pd.read_csv(INTERIM / "totals_long.csv")

    files = {
        f"{PREFIX}_aggregate_long.csv": reporter_cat_long(agg, MAIN_CATS, totals),
        f"{PREFIX}_aggregate_wide.csv": reporter_cat_wide(agg, MAIN_CATS, totals),
        f"{PREFIX}_by_country_long.csv": by_country_long(byc),
        f"{PREFIX}_by_country_wide.csv": by_country_wide(byc),
        f"{PREFIX}_alt_categories_long.csv": reporter_cat_long(alt, ALT_CATS, None),
        f"{PREFIX}_alt_categories_wide.csv": reporter_cat_wide(alt, ALT_CATS, None),
    }
    for name, frame in files.items():
        frame.to_csv(OUT / name, index=False, encoding="utf-8")
        logger.info("wrote %s (%d rows, %d cols)", name, len(frame), frame.shape[1])

    # africa_reporter (BACI) — written by 44_africa_reporter.py; fold in if present.
    ar_long_path = OUT / f"{PREFIX}_africa_reporter_long.csv"
    ar_long = pd.read_csv(ar_long_path) if ar_long_path.exists() else None

    # tidy_all uses the long interim tables (with raw category values)
    tidy = build_tidy_all(agg, byc, alt, totals, ar_long)

    xlsx = OUT / f"{PREFIX}.xlsx"
    sheet_map = {
        "aggregate_long": files[f"{PREFIX}_aggregate_long.csv"],
        "aggregate_wide": files[f"{PREFIX}_aggregate_wide.csv"],
        "by_country_long": files[f"{PREFIX}_by_country_long.csv"],
        "by_country_wide": files[f"{PREFIX}_by_country_wide.csv"],
        "alt_categories_long": files[f"{PREFIX}_alt_categories_long.csv"],
        "alt_categories_wide": files[f"{PREFIX}_alt_categories_wide.csv"],
    }
    # Per-country ALT 7-category breakdown (built by 43_reshape_alt_by_country.py):
    # US/China x 54 AU members + an `AFR / Africa total (54 AU)` row, 7 alt cats +
    # unspecified (HS 99) as columns. Folded in if the CSV is present.
    _bca = OUT / f"{PREFIX}_by_country_alt_categories.csv"
    if _bca.exists():
        sheet_map["by_country_alt_categories"] = pd.read_csv(_bca)
    # BACI (reconciled) counterpart of the above — per-country alt categories,
    # 2000-2024, from 49_baci_by_country_alt.py. Folded in if present.
    _bca_baci = OUT / f"{PREFIX}_by_country_alt_categories_baci.csv"
    if _bca_baci.exists():
        sheet_map["by_country_alt_baci"] = pd.read_csv(_bca_baci)
    if ar_long is not None:
        # africa_reporter wide sheet is rebuilt from long (clean; the on-disk CSV
        # carries a coverage footer that must not leak into the workbook).
        ar_wide = (ar_long.pivot_table(index=["partner_region", "category", "flow"],
                                       columns="Year", values="value_usd", observed=True)
                          .reset_index())
        ar_wide.columns = [str(c) for c in ar_wide.columns]
        ar_totals = (ar_long.groupby(["Year", "flow", "partner_region"], observed=True)["value_usd"]
                            .sum().reset_index())
        # totals pivoted to one column per region (focus regions first)
        _lead = ["USA", "China", "Europe", "Asia_ex_China"]
        ar_totals_wide = (ar_totals.pivot_table(index=["Year", "flow"], columns="partner_region",
                                                values="value_usd", observed=True).reset_index())
        ar_totals_wide.columns.name = None
        _region_cols = ([c for c in _lead if c in ar_totals_wide.columns]
                        + [c for c in ar_totals_wide.columns
                           if c not in _lead + ["Year", "flow"]])
        ar_totals_wide = ar_totals_wide[["Year", "flow"] + _region_cols]
        # percentage version: each region as a share of the row total (sums to 100)
        ar_totals_wide_pct = ar_totals_wide.copy()
        _row_total = ar_totals_wide_pct[_region_cols].sum(axis=1)
        ar_totals_wide_pct[_region_cols] = (ar_totals_wide_pct[_region_cols]
                                            .div(_row_total, axis=0).mul(100).round(2))
        # extra-Africa share view: denominator excludes Intra_Africa, removing the
        # two-way intra double-count so external partner shares are undistorted.
        _extra_cols = [c for c in _region_cols if c != "Intra_Africa"]
        ar_totals_wide_pct_extra = ar_totals_wide[["Year", "flow"] + _extra_cols].copy()
        _extra_total = ar_totals_wide_pct_extra[_extra_cols].sum(axis=1)
        ar_totals_wide_pct_extra[_extra_cols] = (ar_totals_wide_pct_extra[_extra_cols]
                                                 .div(_extra_total, axis=0).mul(100).round(2))
        # Stamp BACI provenance onto the two share sheets so the citation travels
        # with the numbers (text in the first column, below a blank separator).
        _baci_src = ("Source: UN Comtrade bilateral data, reconciled by CEPII "
                     "(BACI V202601, HS92). Nominal USD; goods HS 01-97; coverage 2000-2024.")

        def _stamp(df, extra):
            col0 = df.columns[0]
            return pd.concat([df, pd.DataFrame({col0: ["", _baci_src + extra]})],
                             ignore_index=True)

        sheet_map["africa_reporter_long"] = ar_long
        sheet_map["africa_reporter_totals"] = ar_totals
        sheet_map["africa_reporter_totals_wide"] = ar_totals_wide
        sheet_map["africa_reporter_totals_wide_pct"] = _stamp(
            ar_totals_wide_pct, "  Shares of TOTAL African trade incl. intra-Africa "
            "(two-way double-counts intra; prefer the _wide_pct_extra sheet).")
        sheet_map["africa_reporter_wide_pct_extra"] = _stamp(  # <=31 chars for Excel
            ar_totals_wide_pct_extra, "  Shares of EXTRA-continental African trade "
            "(intra-Africa excluded) — the publication-safe partner-share view.")
        sheet_map["africa_reporter_wide"] = ar_wide

    # Comtrade-mirror shares (single-source cross-check to the BACI africa_reporter
    # sheets) — folded in if 48_africa_reporter_comtrade.py has produced them.
    # Sheet names kept <=31 chars and prefixed `ar_comtrade` to distinguish from
    # the BACI `africa_reporter_*` sheets. Extra-Africa basis; raw (unreconciled),
    # so ~0.85-1.05x the BACI values (Asia lower); 2025 partial. See validation log.
    _cm_pct = OUT / f"{PREFIX}_africa_reporter_comtrade_totals_wide_pct_extra_africa.csv"
    _cm_tot = OUT / f"{PREFIX}_africa_reporter_comtrade_totals_wide.csv"
    if _cm_pct.exists():
        sheet_map["ar_comtrade_pct_extra"] = pd.read_csv(_cm_pct)
    if _cm_tot.exists():
        sheet_map["ar_comtrade_totals_wide"] = pd.read_csv(_cm_tot)

    # External 2025 reference block (GACC China + US Census) — provisional latest-
    # year levels from national sources, folded in if the CSV is present. Not
    # derived from the pipeline; hand-sourced constants (see the CSV's source col).
    ref_path = OUT / "external_reference_2025.csv"
    if ref_path.exists():
        ref = pd.read_csv(ref_path)
        # append a plain-language final-note block below the data (text in the
        # first column; other columns left blank). CSV stays clean data-only.
        _notes = [
            "",
            "NOTES:",
            "Basis: US = exact 54 AU-member definition (matches the rest of this workbook), "
            "computed from fifa_trade_data Census by-country data, 2025 full year. "
            "China = GACC continental Africa (no 54-AU breakdown published).",
            "Continental-vs-54-AU gap = $0.076B = 0.091% of the continental total "
            "(5 dependent territories: Reunion, Mayotte, St. Helena, British Indian Ocean Terr., "
            "French Southern Lands; Western Sahara absent from Census). So China's continental "
            "figure equals the 54-AU basis within <0.1%.",
            "US-Africa 2025 (54-AU) = $83.36B two-way (exports $40.38B / imports $42.98B). "
            "Cross-checks: Census c0013 continental $83.35B (0.1%); Comtrade reporter=US exports ~exact.",
            "Provisional latest-year LEVELS, not shares. China figure is all commodities.",
        ]
        ref = pd.concat([ref, pd.DataFrame({ref.columns[0]: _notes})], ignore_index=True)
        sheet_map["reference_2025"] = ref

    # Compact US-vs-China two-way trade with Africa, one row per year (2000-2025).
    # 2000-2024 from the Comtrade aggregate; 2025 from the external reference
    # (US = US Census, China = GACC) since Comtrade China 2025 is unpublished.
    _tw = files[f"{PREFIX}_aggregate_long.csv"]
    _tw = _tw[_tw["flow"] == "two_way"].copy()
    _tw["Year"] = _tw["Year"].astype(int)
    _tw = _tw.set_index("Year")
    _uc = pd.DataFrame([{"period": y,
                         "US two way trade": _tw["US_Africa_total"].get(y),
                         "China two way trade": _tw["China_Africa_total"].get(y)}
                        for y in range(2000, 2026)])
    _refp = OUT / "external_reference_2025.csv"
    if _refp.exists():
        _r = pd.read_csv(_refp)
        _uc.loc[_uc["period"] == 2025, "US two way trade"] = \
            float(_r.loc[_r["partner"] == "US", "two_way_usd"].iloc[0])
        _uc.loc[_uc["period"] == 2025, "China two way trade"] = \
            float(_r.loc[_r["partner"] == "China", "two_way_usd"].iloc[0])
    _uc = pd.concat([_uc, pd.DataFrame([
        {"period": ""},
        {"period": "2000-2024: UN Comtrade (two-way with Africa). 2025: US = US Census "
                   "($83.36B, 54-AU basis); China = GACC ($348.05B). Nominal USD."}])],
        ignore_index=True)
    sheet_map["us_china_two_way"] = _uc

    # BACI counterpart of the above (reconciled). BACI ends at 2024, so no 2025
    # row — the 2024->2025 jump would be distorted by the BACI(reconciled)->GACC
    # (gross) basis change; for a provisional 2025 use the us_china_two_way sheet.
    _bpath = OUT / f"{PREFIX}_africa_reporter_totals_wide.csv"
    if _bpath.exists():
        _b = pd.read_csv(_bpath)
        _b = _b[_b["flow"] == "two_way"].copy()
        _b["Year"] = _b["Year"].astype(int)
        _b = _b.set_index("Year")
        _ucb = pd.DataFrame([{"period": y,
                              "US two way trade": _b["USA"].get(y),
                              "China two way trade": _b["China"].get(y)}
                             for y in range(2000, 2025)])
        _ucb = pd.concat([_ucb, pd.DataFrame([
            {"period": ""},
            {"period": "Source: BACI (reconciled UN Comtrade, CEPII V202601). Two-way US/China "
                       "with Africa (54 AU), nominal USD. BACI ends 2024; for a provisional 2025 "
                       "see the us_china_two_way sheet (US Census / GACC)."}])], ignore_index=True)
        sheet_map["us_china_two_way_baci"] = _ucb

    sheet_map["tidy_all"] = tidy

    # Front README sheet — quick "use X sheet for Y + caveats + sources" guide.
    # Written header-less so it reads as a one-page document.
    _readme_rows = [
        ["US-CHINA-AFRICA TRADE — MASTER WORKBOOK (README)", "", ""],
        ["Nominal USD; goods only. Full schema: context/03_data_contract.md. "
         "Validation: context/05_validation_log.md.", "", ""],
        ["", "", ""],
        ["SHEET", "USE FOR", "STATUS"],
        ["aggregate_long / _wide", "US & China trade with Africa by year; 4 categories + totals (2000-2025)", "Publication-ready"],
        ["alt_categories_long / _wide", "Same as aggregate, 7-category scheme", "Publication-ready"],
        ["by_country_long / _wide", "US & China trade with each of the 54 AU members (main 4 categories)", "Publication-ready"],
        ["by_country_alt_categories", "US & China by AU country, 7 alt categories (wide) + Africa-total row (Comtrade)", "Publication-ready"],
        ["by_country_alt_baci", "Same as above but BACI (reconciled), 2000-2024, no ch99", "Publication-ready (BACI)"],
        ["africa_reporter_wide_pct_extra", "PARTNER SHARES of African trade (extra-continental) — headline shares (2000-2024)", "Publication-ready (BACI)"],
        ["africa_reporter_totals_wide_pct", "Partner shares incl. intra-Africa (two-way double-counts intra; prefer _extra)", "Use with caution"],
        ["africa_reporter_totals_wide / _totals / _long / _wide", "BACI region totals (USD) & category detail", "Publication-ready (BACI)"],
        ["ar_comtrade_pct_extra / _totals_wide", "Raw Comtrade cross-check to BACI — undercounts non-reporters", "Cross-check only — do NOT publish"],
        ["us_china_two_way", "US vs China two-way trade with Africa, one row/year (2000-2025; Comtrade, 2025 = Census/GACC)", "Publication-ready"],
        ["us_china_two_way_baci", "Same as above but BACI (reconciled), 2000-2024 (BACI has no 2025)", "Publication-ready (BACI)"],
        ["reference_2025", "Provisional 2025 LEVELS: China $348B (GACC), US $83.36B (Census) — not shares", "Provisional"],
        ["tidy_all", "All datasets in one normalized long table", "Convenience"],
        ["", "", ""],
        ["KEY CAVEATS", "", ""],
        ["China 2025 is blank in the Comtrade series (unpublished). 2025 China = reference_2025 (GACC).", "", ""],
        ["Partner shares (BACI) end at 2024. For a 2025 point use reference_2025 levels or a nowcast.", "", ""],
        ["For partner shares use africa_reporter_wide_pct_extra; the _totals_wide_pct sheet double-counts intra-Africa in two-way.", "", ""],
        ["ar_comtrade_* are a transparency cross-check only — do not publish those shares.", "", ""],
        ["", "", ""],
        ["SOURCES", "", ""],
        ["Partner shares & region totals", "UN Comtrade bilateral data, reconciled by CEPII (BACI V202601, HS92)", ""],
        ["US & China series", "UN Comtrade (reporter=US 842 / China 156); US = US Census equivalent", ""],
        ["2025 reference — China", "GACC (China General Administration of Customs)", ""],
        ["2025 reference — US", "US Census Bureau, 54-AU basis via fifa_trade_data", ""],
    ]
    _readme = pd.DataFrame(_readme_rows, columns=["c1", "c2", "c3"])
    sheet_map = {"README": _readme, **sheet_map}  # README first

    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        for sheet, frame in sheet_map.items():
            frame.to_excel(writer, sheet_name=sheet, index=False, header=(sheet != "README"))
    ar_note = "incl. africa_reporter" if ar_long is not None else "africa_reporter absent (run 44)"
    logger.info("wrote %s (%d sheets; %s)", xlsx.name, len(sheet_map), ar_note)

    if totals["World_ex_Africa_total"].isna().all():
        logger.warning("World_ex_Africa_total columns are blank — run reporter_world fetch + 25_totals to fill.")


if __name__ == "__main__":
    main()
