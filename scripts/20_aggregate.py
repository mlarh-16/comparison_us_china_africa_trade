"""Aggregate raw Comtrade cells into tidy interim tables.

Reads the raw JSON cached by 10_fetch_comtrade.py and produces normalised long
tables under interim/. Totals (25_totals.py) and final output shapes / the Excel
workbook (30_build_outputs.py) are built downstream from these.

Built here (all from the reporter_partner cache, which is complete):
  interim/aggregate_main_long.csv   main 4-cat, 54 AU partners summed to Africa
  interim/by_country_long.csv       main 4-cat, per AU member
  interim/alt_categories_long.csv   alt 7-cat, summed to Africa

The 8-region africa_reporter table is NOT built here yet: its raw cache is still
partial (resume the fetch) and the mirror-fallback source rule needs settling
(only the USA/China regions are mirrorable from our reporter_partner pull; other
regions would need their own reporter data). Tracked as the next sub-task.

Conventions (data contract):
  - Nominal USD, value column = Comtrade `primaryValue`.
  - flow in {imports, exports, two_way}; two_way = imports + exports (derived).
  - HS chapter 99 (and anything outside 01-97) is dropped from category sums.
  - Codes are strings; partnerCode ints are zero-padded to 3 digits to match config.

Run: conda run -n us_china_africa_trade python scripts/20_aggregate.py
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
FLOW_ORDER = ["imports", "exports", "two_way"]

# 2024 two-way aggregate benchmarks (control room / data contract).
BENCHMARKS_2024 = {"US": 72_576_740_427, "China": 295_366_109_606}
# The benchmarks are the official TOTAL line, which INCLUDES chapter 99
# ("commodities nes"). The 4 categories cover HS 01-97 only, so the benchmark
# check reconstructs all chapters incl. 99 and expects a near-exact match.
BENCHMARK_TOL = 0.001  # 0.1%


# ---------------------------------------------------------------------------
# Chapter -> category lookups (reverse of the config maps)
# ---------------------------------------------------------------------------
def _reverse(scheme: dict) -> dict:
    return {ch: cat for cat, chapters in scheme.items() for ch in chapters}


CH_TO_MAIN = _reverse(config.HS_CATEGORY_MAP_MAIN)
CH_TO_ALT = _reverse(config.HS_CATEGORY_MAP_ALT)

# Chapter 99 ("commodities nes") and any code outside HS 01-97 are not part of
# either sector scheme. Per the 2026-06-15 "show both" decision they are kept as
# a labelled line so totals reconcile to the official Comtrade total.
UNSPECIFIED = "unspecified (HS 99)"


def assign_category(d: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    """Map chapter -> category; unmapped codes (ch99 etc.) become UNSPECIFIED."""
    cat = d["chapter"].map(lookup)
    unmapped = sorted(d.loc[cat.isna(), "chapter"].dropna().unique())
    if unmapped and set(unmapped) - {"99"}:
        logger.warning("Unmapped HS chapters bucketed to '%s': %s", UNSPECIFIED, unmapped)
    out = d.copy()
    out["category"] = cat.fillna(UNSPECIFIED)
    return out


# ---------------------------------------------------------------------------
# Load the reporter_partner cache into one tidy frame
# ---------------------------------------------------------------------------
def load_reporter_partner() -> pd.DataFrame:
    """One row per (reporter, year, flow, country, chapter) with USD value.

    ALL 2-digit chapters are kept here, including chapter 99 ("commodities
    nes"). Chapter 99 is excluded from the category tables (its chapter maps to
    no category, so it drops out at bucketing) but retained in this frame so the
    benchmark check can reconstruct the official total, which includes it.
    partner2Code != 0 breakdowns are excluded so values are not double counted.
    """
    cache_dir = config.Paths.raw_data / "reporter_partner"
    files = sorted(cache_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No reporter_partner cache in {cache_dir}. Run the fetcher first.")

    records: list[dict] = []
    for f in files:
        label, year, flow = f.stem.split("_")  # e.g. China_2022_imports
        body = json.loads(f.read_text(encoding="utf-8"))
        for row in body.get("data") or []:
            if row.get("partner2Code", 0) not in (0, None):
                continue
            value = row.get("primaryValue")
            if value is None:
                continue
            partner3 = f"{int(row['partnerCode']):03d}"
            meta = config.AFRICA_AU_COUNTRIES.get(partner3)
            if meta is None:
                continue  # partner not in the AU list (shouldn't happen for this setup)
            records.append({
                "reporter": label,
                "year": int(year),
                "flow": flow,
                "country_iso3": meta["iso3"],
                "country_name": meta["name"],
                "chapter": row.get("cmdCode"),
                "value_usd": float(value),
            })

    df = pd.DataFrame.from_records(records)
    logger.info("Loaded %d reporter_partner rows from %d files", len(df), len(files))
    return df


# ---------------------------------------------------------------------------
# two_way = imports + exports (derived), appended as a third flow
# ---------------------------------------------------------------------------
def add_two_way(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    # two_way = imports + exports summed over each identity key. `flow` must NOT
    # be a grouping key here, or imports and exports stay in separate groups and
    # get emitted as two duplicate two_way rows instead of one summed row.
    keys = [c for c in group_cols if c != "flow"]
    two = (df[df["flow"].isin(["imports", "exports"])]
           .groupby(keys, as_index=False)["value_usd"].sum())
    two["flow"] = "two_way"
    out = pd.concat([df, two[df.columns]], ignore_index=True)
    out["flow"] = pd.Categorical(out["flow"], categories=FLOW_ORDER, ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Build the three tables
# ---------------------------------------------------------------------------
def build_aggregate_main(df: pd.DataFrame) -> pd.DataFrame:
    d = assign_category(df, CH_TO_MAIN)
    g = (d.groupby(["year", "flow", "reporter", "category"], as_index=False)["value_usd"].sum())
    return add_two_way(g, ["year", "flow", "reporter", "category"])


def build_by_country(df: pd.DataFrame) -> pd.DataFrame:
    d = assign_category(df, CH_TO_MAIN)
    g = (d.groupby(["year", "flow", "reporter", "country_iso3", "country_name", "category"],
                   as_index=False)["value_usd"].sum())
    return add_two_way(g, ["year", "flow", "reporter", "country_iso3", "country_name", "category"])


def build_alt(df: pd.DataFrame) -> pd.DataFrame:
    d = assign_category(df, CH_TO_ALT)
    g = (d.groupby(["year", "flow", "reporter", "category"], as_index=False)["value_usd"].sum())
    return add_two_way(g, ["year", "flow", "reporter", "category"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame, agg_main: pd.DataFrame, by_country: pd.DataFrame,
             alt: pd.DataFrame) -> None:
    logger.info("--- validation ---")

    # No negative values
    for name, t in [("aggregate", agg_main), ("by_country", by_country), ("alt", alt)]:
        neg = (t["value_usd"] < 0).sum()
        logger.info("%s: rows=%d, negative values=%d", name, len(t), neg)

    # 2024 two-way benchmark: reconstruct the official total (ALL chapters incl
    # 99) from the raw frame, since the benchmark includes chapter 99.
    raw24 = df[df["year"] == 2024]
    for reporter, expected in BENCHMARKS_2024.items():
        r = raw24[raw24["reporter"] == reporter]
        two_way_all = r[r["flow"].isin(["imports", "exports"])]["value_usd"].sum()
        ch99 = r[(r["flow"].isin(["imports", "exports"])) & (r["chapter"] == "99")]["value_usd"].sum()
        delta = (two_way_all - expected) / expected if expected else float("nan")
        status = "PASS" if abs(delta) <= BENCHMARK_TOL else "FLAG"
        logger.info("2024 two-way %-5s: expected %s actual(incl ch99) %s (ch99=%s) delta %+.3f%% [%s]",
                    reporter, f"{expected:,.0f}", f"{two_way_all:,.0f}", f"{ch99:,.0f}",
                    delta * 100, status)

    # Reconciliation: aggregate_main (all categories incl. unspecified) == benchmark
    am24 = agg_main[(agg_main["flow"] == "two_way") & (agg_main["year"] == 2024)]
    for reporter, expected in BENCHMARKS_2024.items():
        total = am24[am24["reporter"] == reporter]["value_usd"].sum()
        unspec = am24[(am24["reporter"] == reporter) & (am24["category"] == UNSPECIFIED)]["value_usd"].sum()
        delta = (total - expected) / expected if expected else float("nan")
        status = "PASS" if abs(delta) <= BENCHMARK_TOL else "FLAG"
        logger.info("2024 Africa_total %-5s (cats+unspec): %s vs benchmark %s (unspec=%s) [%s]",
                    reporter, f"{total:,.0f}", f"{expected:,.0f}", f"{unspec:,.0f}", status)

    # Cross-scheme: alt categories sum == main categories sum, per reporter/year/flow
    a = alt.groupby(["year", "flow", "reporter"])["value_usd"].sum().rename("alt")
    m = agg_main.groupby(["year", "flow", "reporter"])["value_usd"].sum().rename("main")
    j = pd.concat([a, m], axis=1).dropna()
    bad = j[(j["alt"] - j["main"]).abs() > 1.0]
    logger.info("cross-scheme alt==main mismatches (> $1): %d of %d groups", len(bad), len(j))

    # Coverage: reporters x years present
    yrs = sorted(agg_main["year"].unique())
    logger.info("years present: %d (%d..%d); reporters: %s",
                len(yrs), min(yrs), max(yrs), sorted(agg_main["reporter"].unique()))


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    df = load_reporter_partner()

    agg_main = build_aggregate_main(df)
    by_country = build_by_country(df)
    alt = build_alt(df)

    agg_main.to_csv(INTERIM / "aggregate_main_long.csv", index=False, encoding="utf-8")
    by_country.to_csv(INTERIM / "by_country_long.csv", index=False, encoding="utf-8")
    alt.to_csv(INTERIM / "alt_categories_long.csv", index=False, encoding="utf-8")
    logger.info("Wrote 3 interim tables to %s", INTERIM)

    validate(df, agg_main, by_country, alt)


if __name__ == "__main__":
    main()
