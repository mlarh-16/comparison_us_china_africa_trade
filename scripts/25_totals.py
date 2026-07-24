"""Compute the total lines for the aggregate dataset.

Adds, per (year, flow, reporter):
  Africa_total            = reporter's total trade with Africa, INCLUDING ch99
                            (= sum of all category rows in the interim aggregate;
                            sector categories + `unspecified (HS 99)`). Matches
                            the official Comtrade benchmark exactly.
  World_ex_Africa_total   = reporter's World total (partner 0) minus Africa_total.
                            Needs the `reporter_world` raw cache. Left blank where
                            that cache is missing (resume the fetch to fill it).

Writes interim/totals_long.csv: year, flow, reporter, Africa_total, World_ex_Africa_total.

Run: conda run -n us_china_africa_trade python scripts/25_totals.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402
from scripts.logger import logger  # noqa: E402

INTERIM = config.Paths.project / "interim"


def world_totals() -> pd.DataFrame:
    """Sum the reporter_world cache (partner 0, all chapters incl. 99) per
    reporter/year/flow. Returns an empty frame if the cache is absent."""
    cache_dir = config.Paths.raw_data / "reporter_world"
    files = sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []
    if not files:
        logger.warning("No reporter_world cache yet — World_ex_Africa_total will be blank. "
                       "Run the fetcher (reporter_world setup) to fill it.")
        return pd.DataFrame(columns=["year", "flow", "reporter", "world_total"])

    rows = []
    for f in files:
        reporter, year, flow = f.stem.split("_")
        body = json.loads(f.read_text(encoding="utf-8"))
        total = 0.0
        for row in body.get("data") or []:
            if row.get("partner2Code", 0) not in (0, None):
                continue
            total += row.get("primaryValue") or 0.0
        rows.append({"year": int(year), "flow": flow, "reporter": reporter, "world_total": total})
    logger.info("Loaded reporter_world totals from %d files", len(files))
    return pd.DataFrame(rows)


def main() -> None:
    agg = pd.read_csv(INTERIM / "aggregate_main_long.csv")

    # Africa_total = all categories (incl. unspecified ch99), imports/exports only;
    # two_way is recomputed so it stays consistent.
    base = agg[agg["flow"].isin(["imports", "exports"])]
    africa = base.groupby(["year", "flow", "reporter"], as_index=False)["value_usd"].sum()
    africa = africa.rename(columns={"value_usd": "Africa_total"})

    world = world_totals()
    if not world.empty:
        w = world[world["flow"].isin(["imports", "exports"])]
        merged = africa.merge(w, on=["year", "flow", "reporter"], how="left")
        merged["World_ex_Africa_total"] = merged["world_total"] - merged["Africa_total"]
        merged = merged.drop(columns=["world_total"])
    else:
        merged = africa.copy()
        merged["World_ex_Africa_total"] = pd.NA

    # two_way row = imports + exports for each total
    two = (merged.groupby(["year", "reporter"], as_index=False)[["Africa_total", "World_ex_Africa_total"]]
           .sum(min_count=1))
    two["flow"] = "two_way"
    out = pd.concat([merged, two[merged.columns]], ignore_index=True)
    out = out.sort_values(["reporter", "year", "flow"]).reset_index(drop=True)

    out.to_csv(INTERIM / "totals_long.csv", index=False, encoding="utf-8")
    logger.info("Wrote %s (%d rows)", INTERIM / "totals_long.csv", len(out))

    have_world = out["World_ex_Africa_total"].notna().any()
    logger.info("Africa_total: populated. World_ex_Africa_total: %s",
                "populated" if have_world else "BLANK (reporter_world not fetched)")
    # quick echo of 2024 two-way
    chk = out[(out["year"] == 2024) & (out["flow"] == "two_way")]
    for _, r in chk.iterrows():
        logger.info("  2024 two-way %-5s Africa_total=%s", r["reporter"], f"{r['Africa_total']:,.0f}")


if __name__ == "__main__":
    main()
