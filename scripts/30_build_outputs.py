"""Write the final CSVs and the master Excel workbook.

Builds the US/China datasets from the interim tables (20_aggregate.py) and the
totals (25_totals.py):

  output/us_china_africa_trade_aggregate_long.csv      / _wide.csv
  output/us_china_africa_trade_by_country_long.csv     / _wide.csv
  output/us_china_africa_trade_alt_categories_long.csv / _wide.csv
  output/us_china_africa_trade.xlsx                    (sheets above + tidy_all)

The two africa_reporter outputs (and their workbook sheets) are NOT written yet —
that dataset's fetch is still in progress. The workbook is regenerated whole on
every run, so it will gain those sheets once the data exists.

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
MAIN_CATS = ["agricultural goods", "mined goods", "apparel",
             "other manufactured goods", "unspecified (HS 99)"]
ALT_CATS = ["raw agrifood", "processed agrifood", "energy minerals", "critical minerals",
            "precious metals & stones", "apparel", "other manufactured", "unspecified (HS 99)"]
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
                   totals: pd.DataFrame) -> pd.DataFrame:
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

    out = pd.concat([a[cols], t[cols], b[cols], al[cols]], ignore_index=True)
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

    # tidy_all uses the long interim tables (with raw category values)
    tidy = build_tidy_all(agg, byc, alt, totals)

    xlsx = OUT / f"{PREFIX}.xlsx"
    sheet_map = {
        "aggregate_long": files[f"{PREFIX}_aggregate_long.csv"],
        "aggregate_wide": files[f"{PREFIX}_aggregate_wide.csv"],
        "by_country_long": files[f"{PREFIX}_by_country_long.csv"],
        "by_country_wide": files[f"{PREFIX}_by_country_wide.csv"],
        "alt_categories_long": files[f"{PREFIX}_alt_categories_long.csv"],
        "alt_categories_wide": files[f"{PREFIX}_alt_categories_wide.csv"],
        "tidy_all": tidy,
    }
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        for sheet, frame in sheet_map.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
    logger.info("wrote %s (%d sheets; africa_reporter sheets pending fetch)", xlsx.name, len(sheet_map))

    if totals["World_ex_Africa_total"].isna().all():
        logger.warning("World_ex_Africa_total columns are blank — run reporter_world fetch + 25_totals to fill.")


if __name__ == "__main__":
    main()
