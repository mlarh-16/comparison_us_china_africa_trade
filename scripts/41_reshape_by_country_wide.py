"""Reshape by_country_long into a category-columns layout.

From: Year, flow, reporter, country_iso3, country_name, category, value_usd
To:   Year, flow, reporter, country_iso3, country_name, <one column per category>

The 5 main-scheme categories (incl. unspecified HS 99) become columns. A
(country, year, flow) with no trade in a category gets 0 (the long file omits
zero-trade rows). Read-only on outputs; writes to output/.
"""

import pandas as pd

from config import Paths

SRC = Paths.output / "us_china_africa_trade_by_country_long.csv"
DEST = Paths.output / "us_china_africa_trade_by_country_categories.csv"

ID_COLS = ["Year", "flow", "reporter", "country_iso3", "country_name"]

# Category column order (left -> right).
CATEGORIES = [
    "agricultural goods",
    "minerals & metals",
    "apparel",
    "other manufactured goods",
    "unspecified (HS 99)",
]


def main() -> None:
    df = pd.read_csv(SRC)

    wide = df.pivot_table(
        index=ID_COLS,
        columns="category",
        values="value_usd",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide.columns.name = None

    wide = wide[ID_COLS + CATEGORIES]

    # Append a continent-wide "Africa total" row per (Year, flow, reporter):
    # the 54 AU members summed. Should equal the aggregate output downstream.
    totals = wide.groupby(["Year", "flow", "reporter"], as_index=False)[CATEGORIES].sum()
    totals["country_iso3"] = "AFR"
    totals["country_name"] = "Africa total (54 AU)"
    wide = pd.concat([wide, totals[ID_COLS + CATEGORIES]], ignore_index=True)

    wide = wide.sort_values(["reporter", "country_iso3", "Year", "flow"]).reset_index(drop=True)

    wide.to_csv(DEST, index=False)
    print(f"{DEST.name}: {wide.shape[0]} rows x {len(CATEGORIES)} category columns "
          f"({(wide['country_iso3'] == 'AFR').sum()} Africa-total rows)")


if __name__ == "__main__":
    main()
