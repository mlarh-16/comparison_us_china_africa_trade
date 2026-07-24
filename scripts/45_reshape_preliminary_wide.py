"""Reshape the PRELIMINARY Africa-reporter CSV to regions-as-columns.

Reads the long preliminary file and writes two wide CSVs (rows = Year x flow,
columns = the 8 regions + residual):
  ..._regions_usd.csv     values = value_usd
  ..._regions_share.csv   values = share_pct (within Year x flow, sums to 100)

Same PRELIMINARY / partial-panel caveats as the source file. Read-only on
outputs; writes to output/.
"""

import pandas as pd

from config import Paths

SRC = Paths.output / "us_china_africa_trade_africa_reporter_PRELIMINARY.csv"
DEST_USD = Paths.output / "us_china_africa_trade_africa_reporter_PRELIMINARY_regions_usd.csv"
DEST_SHARE = Paths.output / "us_china_africa_trade_africa_reporter_PRELIMINARY_regions_share.csv"

REGION_ORDER = [
    "USA", "China", "Europe", "Asia_ex_China", "Intra_Africa",
    "S_America", "N_America_ex_US", "Oceania", "Other_residual (nes/bunkers)",
]
FLOW_ORDER = ["imports", "exports", "two_way"]


def _wide(df: pd.DataFrame, value_col: str, dest) -> None:
    w = df.pivot_table(index=["Year", "flow"], columns="partner_region",
                       values=value_col, fill_value=0).reset_index()
    w.columns.name = None
    cols = ["Year", "flow"] + [r for r in REGION_ORDER if r in w.columns]
    w = w[cols]
    w["flow"] = pd.Categorical(w["flow"], FLOW_ORDER, ordered=True)
    w = w.sort_values(["flow", "Year"]).reset_index(drop=True)
    w.to_csv(dest, index=False, encoding="utf-8")
    print(f"{dest.name}: {w.shape[0]} rows x {len(cols) - 2} region columns")


def main() -> None:
    df = pd.read_csv(SRC)
    _wide(df, "value_usd", DEST_USD)
    _wide(df, "share_pct", DEST_SHARE)


if __name__ == "__main__":
    main()
