"""Reshape the alt 7-category aggregate file into Flourish stacked-chart CSVs.

One CSV per flow (imports, exports), HS 99 kept. Output shape:
rows = (Year, reporter), columns = Year, reporter, then the 8 stack segments
(7 sectors + unspecified HS 99). Both reporters stacked into one file via a
`reporter` column (China / US) so Flourish can filter or facet on it.

Read-only on the pipeline outputs; writes to output/flourish/.
"""

import pandas as pd

from config import Paths

SRC = Paths.output / "us_china_africa_trade_alt_categories_long.csv"
OUT_DIR = Paths.output / "flourish"

FLOWS = ["imports", "exports"]

# Stack segment order (bottom -> top). Sectors first, unspecified last.
CATEGORIES = [
    "raw agrifood",
    "processed agrifood",
    "energy minerals",
    "critical minerals",
    "precious metals & stones",
    "apparel",
    "other manufactured",
    "unspecified (HS 99)",
]

REPORTERS = ["China", "US"]


def main() -> None:
    df = pd.read_csv(SRC)
    OUT_DIR.mkdir(exist_ok=True)

    for flow in FLOWS:
        sub = df[df["flow"] == flow]
        parts = []
        for reporter in REPORTERS:
            cols = [f"{reporter} {cat}" for cat in CATEGORIES]
            part = sub[["Year"] + cols].copy()
            # Strip the reporter prefix so segment names are just the category.
            part.columns = ["Year"] + CATEGORIES
            part.insert(1, "reporter", reporter)
            parts.append(part)

        out = pd.concat(parts, ignore_index=True)
        out = out.sort_values(["reporter", "Year"]).reset_index(drop=True)

        dest = OUT_DIR / f"alt_{flow}_stacked.csv"
        out.to_csv(dest, index=False)
        print(f"{dest.name}: {out.shape[0]} rows ({len(REPORTERS)} reporters x years) "
              f"x {len(CATEGORIES)} segments")


if __name__ == "__main__":
    main()
