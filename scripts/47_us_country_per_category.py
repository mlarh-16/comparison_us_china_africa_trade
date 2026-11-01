"""Top-7 AU countries per Year x flow x category, US reporter, both schemes.

Output: output/us_country_per_category.csv
Columns: scheme, flow, category, Year, rank, country_iso3, country_name, value_usd

Ranking: within each (scheme, flow, category, Year), AU members are ranked by
US trade value descending; the top 7 (positive values only) are kept. Covers
the main 4-cat scheme and the alt 7-cat scheme, each incl. 'unspecified (HS 99)'.

Sources the per-country category files (main + alt). Read-only; writes to output/.
Run: conda run -n us_china_africa_trade python scripts/47_us_country_per_category.py
"""

import pandas as pd

from config import Paths

SRC_MAIN = Paths.output / "us_china_africa_trade_by_country_categories.csv"
SRC_ALT = Paths.output / "us_china_africa_trade_by_country_alt_categories.csv"
DEST = Paths.output / "us_country_per_category.csv"

ID = ["Year", "flow", "reporter", "country_iso3", "country_name"]
TOP_N = 7
FLOW_ORDER = ["imports", "exports", "two_way"]

MAIN_CATS = ["agricultural goods", "minerals & metals", "apparel",
             "other manufactured goods", "unspecified (HS 99)"]
ALT_CATS = ["raw agrifood", "processed agrifood", "energy minerals",
            "unrefined minerals", "refined minerals", "apparel",
            "other manufactured", "unspecified (HS 99)"]


def to_long(path, cats, scheme) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[(df["reporter"] == "US") & (df["country_iso3"] != "AFR")]  # US only, drop Africa-total rows
    long = df.melt(id_vars=ID, value_vars=cats,
                   var_name="category", value_name="value_usd")
    long["scheme"] = scheme
    return long


def rank_top(long: pd.DataFrame) -> pd.DataFrame:
    long = long[long["value_usd"] > 0].copy()
    long = long.sort_values(["scheme", "flow", "category", "Year", "value_usd"],
                            ascending=[True, True, True, True, False])
    long["rank"] = long.groupby(["scheme", "flow", "category", "Year"]).cumcount() + 1
    return long[long["rank"] <= TOP_N]


def main() -> None:
    main_long = to_long(SRC_MAIN, MAIN_CATS, "main_4")
    alt_long = to_long(SRC_ALT, ALT_CATS, "alt_7")
    out = rank_top(pd.concat([main_long, alt_long], ignore_index=True))

    out["flow"] = pd.Categorical(out["flow"], FLOW_ORDER, ordered=True)
    out = out.sort_values(["scheme", "flow", "category", "Year", "rank"])
    out = out[["scheme", "flow", "category", "Year", "rank",
               "country_iso3", "country_name", "value_usd"]].reset_index(drop=True)

    out.to_csv(DEST, index=False, encoding="utf-8")
    print(f"{DEST.name}: {len(out)} rows")
    print("schemes:", out["scheme"].unique().tolist())
    print("categories:", out["category"].nunique(),
          "| flows:", out["flow"].cat.categories.tolist(),
          "| years:", out["Year"].min(), "-", out["Year"].max())
    print("max rank:", out["rank"].max())


if __name__ == "__main__":
    main()
