"""Reshape the alt 7-category aggregate file into Flourish stacked-chart CSVs.

Writes four files, HS 99 kept, 8 stack segments (7 sectors + unspecified HS 99):
  - alt_imports_stacked.csv / alt_exports_stacked.csv
      rows = (Year, reporter); columns = Year, reporter, then the 8 segments.
      Both reporters stacked into one file via a `reporter` column so Flourish
      can filter or facet on it.
  - alt_china_two_way_stacked.csv / alt_us_two_way_stacked.csv
      one file per reporter, two_way flow; columns = Year, then the 8 segments.

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
    "unrefined minerals",
    "refined minerals",
    "apparel",
    "other manufactured",
    "unspecified (HS 99)",
]

REPORTERS = ["China", "US"]


def main() -> None:
    df = pd.read_csv(SRC)
    OUT_DIR.mkdir(exist_ok=True)

    # imports / exports: both reporters in one file via a `reporter` column.
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

    # two_way: one file per reporter (Year + 8 segments, no reporter column).
    tw = df[df["flow"] == "two_way"]
    for reporter in REPORTERS:
        cols = [f"{reporter} {cat}" for cat in CATEGORIES]
        part = tw[["Year"] + cols].copy()
        part.columns = ["Year"] + CATEGORIES
        part = part.sort_values("Year").reset_index(drop=True)

        dest = OUT_DIR / f"alt_{reporter.lower()}_two_way_stacked.csv"
        part.to_csv(dest, index=False)
        print(f"{dest.name}: {part.shape[0]} rows (years) x {len(CATEGORIES)} segments")


if __name__ == "__main__":
    main()
