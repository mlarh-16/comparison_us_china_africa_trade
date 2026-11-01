"""Per-African-country x alt-category trade with US & China, from BACI (reconciled).

BACI counterpart of `us_china_africa_trade_by_country_alt_categories.csv` (which
is Comtrade). Source: `raw_data/baci/baci_uschina_by_country_slice.csv` — the
per-AU-member, US/China-partner slice added to `12_fetch_baci.py`. Reconciled
bilateral values; 2000-2024; classified HS 01-97 (BACI has no chapter 99, so
there is no `unspecified (HS 99)` column).

Flow convention matches the Comtrade by_country sheet — the US/China REPORTER's
perspective: `flow=imports` = US/China imports FROM the African country
(= BACI 'exports', Africa->partner); `flow=exports` = US/China exports TO it.

Output: `output/us_china_africa_trade_by_country_alt_categories_baci.csv`
Run: conda run -n us_china_africa_trade python scripts/49_baci_by_country_alt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

SLICE = config.Paths.raw_data / "baci" / "baci_uschina_by_country_slice.csv"
OUT = config.Paths.output / "us_china_africa_trade_by_country_alt_categories_baci.csv"

ALT_ORDER = list(config.HS_CATEGORY_MAP_ALT.keys())  # 7 alt categories (no ch99 in BACI)
CH2ALT = {ch: cat for cat, chs in config.HS_CATEGORY_MAP_ALT.items() for ch in chs}
ISO2NAME = {v["iso3"]: v["name"] for v in config.AFRICA_AU_COUNTRIES.values()}
PARTNER2REP = {"USA": "US", "CHN": "China"}
FLOW_FLIP = {"exports": "imports", "imports": "exports"}  # Africa persp. -> reporter persp.
FLOW_ORDER = ["imports", "exports", "two_way"]


def main() -> None:
    df = pd.read_csv(SLICE, dtype={"hs2": "string", "au_iso3": "string",
                                   "partner_iso3": "string"})
    df["category"] = df["hs2"].map(CH2ALT)
    unmapped = sorted(set(df.loc[df["category"].isna(), "hs2"].dropna()))
    assert not unmapped, f"unmapped HS2 chapters: {unmapped}"
    df["reporter"] = df["partner_iso3"].map(PARTNER2REP)
    df["flow"] = df["flow"].map(FLOW_FLIP)
    df = df.rename(columns={"au_iso3": "country_iso3", "year": "Year"})

    keys = ["Year", "flow", "reporter", "country_iso3", "category"]
    long = df.groupby(keys, observed=True)["value_usd"].sum().reset_index()

    # two_way = imports + exports (per country x category)
    tw = (long.groupby(["Year", "reporter", "country_iso3", "category"], observed=True)
              ["value_usd"].sum().reset_index())
    tw["flow"] = "two_way"
    long = pd.concat([long, tw[long.columns]], ignore_index=True)

    # Africa-total rows (sum across the 54 countries), for each Year x flow x reporter
    afr = (long.groupby(["Year", "flow", "reporter", "category"], observed=True)
               ["value_usd"].sum().reset_index())
    afr["country_iso3"] = "AFR"
    long = pd.concat([long, afr[long.columns]], ignore_index=True)

    # categories -> columns
    wide = (long.pivot_table(index=["Year", "flow", "reporter", "country_iso3"],
                             columns="category", values="value_usd", observed=True)
                .reset_index())
    wide.columns.name = None
    for c in ALT_ORDER:
        if c not in wide.columns:
            wide[c] = 0.0
    wide[ALT_ORDER] = wide[ALT_ORDER].fillna(0.0)
    wide["country_name"] = wide["country_iso3"].map(
        lambda i: "Africa total (54 AU)" if i == "AFR" else ISO2NAME.get(i, i))
    wide["flow"] = pd.Categorical(wide["flow"], FLOW_ORDER, ordered=True)
    wide = wide.sort_values(["Year", "flow", "reporter", "country_iso3"]).reset_index(drop=True)
    wide = wide[["Year", "flow", "reporter", "country_iso3", "country_name"] + ALT_ORDER]

    assert (wide[ALT_ORDER].values < 0).sum() == 0, "negative values present"
    wide.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {OUT.name}: {len(wide)} rows, "
          f"{wide['country_iso3'].nunique()} countries (incl AFR), "
          f"years {wide['Year'].min()}-{wide['Year'].max()}, source=baci_reconciled")


if __name__ == "__main__":
    main()
