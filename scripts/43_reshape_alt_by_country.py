"""Per-country ALT 7-cat table, categories as columns (side deliverable).

NOTE: per-country outputs under the alt scheme are OUT of the locked scope
(alt is aggregate-Africa only in the data contract). This is an ad-hoc derived
file, not an official pipeline output, and is not registered in the contract.

Re-buckets the raw reporter_partner cache with the ALT map at country level,
then pivots category -> columns. Reuses 20_aggregate.py's loader/bucketing so
values match the pipeline exactly.

Output: output/us_china_africa_trade_by_country_alt_categories.csv
Cols: Year, flow, reporter, country_iso3, country_name + 8 alt category columns.

Run: conda run -n us_china_africa_trade python scripts/43_reshape_alt_by_country.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from config import Paths

# Import the digit-prefixed aggregator module by path (not a valid identifier).
_spec = importlib.util.spec_from_file_location(
    "aggregate20", Paths.scripts / "20_aggregate.py"
)
agg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agg)

DEST = Paths.output / "us_china_africa_trade_by_country_alt_categories.csv"

ID_COLS = ["Year", "flow", "reporter", "country_iso3", "country_name"]
KEY = ["year", "flow", "reporter", "country_iso3", "country_name", "category"]

# Alt category column order (left -> right): 7 sectors + unspecified HS 99.
CATEGORIES = [
    "raw agrifood",
    "processed agrifood",
    "energy minerals",
    "critical minerals",
    "precious metals & stones",
    "apparel",
    "other manufactured",
    agg.UNSPECIFIED,
]


def main() -> None:
    df = agg.load_reporter_partner()
    d = agg.assign_category(df, agg.CH_TO_ALT)
    g = d.groupby(KEY, as_index=False)["value_usd"].sum()
    g = agg.add_two_way(g, KEY)

    wide = g.pivot_table(
        index=["year", "flow", "reporter", "country_iso3", "country_name"],
        columns="category",
        values="value_usd",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide.columns.name = None

    wide = wide.rename(columns={"year": "Year"})
    wide = wide[ID_COLS + CATEGORIES]

    # Append a continent-wide "Africa total" row per (Year, flow, reporter):
    # the 54 AU members summed. Should equal the alt aggregate output downstream.
    totals = wide.groupby(["Year", "flow", "reporter"], as_index=False)[CATEGORIES].sum()
    totals["country_iso3"] = "AFR"
    totals["country_name"] = "Africa total (54 AU)"
    wide = pd.concat([wide, totals[ID_COLS + CATEGORIES]], ignore_index=True)

    wide = wide.sort_values(["reporter", "country_iso3", "Year", "flow"]).reset_index(drop=True)

    wide.to_csv(DEST, index=False, encoding="utf-8")
    print(f"{DEST.name}: {wide.shape[0]} rows x {len(CATEGORIES)} alt category columns "
          f"({(wide['country_iso3'] == 'AFR').sum()} Africa-total rows)")


if __name__ == "__main__":
    main()
