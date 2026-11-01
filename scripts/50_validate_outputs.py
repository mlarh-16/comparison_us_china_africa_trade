"""Validate the on-disk outputs against the data contract and benchmarks.

Re-runs every check on the CURRENT files in output/ (not on interim state):
  - 2024 two-way external benchmarks (US 72.58B, China 295.37B).
  - World_ex_Africa_total independently reconstructed from the reporter_world
    raw cache (world total - Africa_total) and compared to the CSV to the dollar.
  - two_way = imports + exports everywhere.
  - Africa_total = sector cats + unspecified, per reporter/year/flow.
  - Cross-scheme: alt 7 sector sum == main 4 sector sum.
  - by_country sums up to the aggregate categories.
  - No negatives; no duplicate keys; row counts; year/reporter coverage.
  - africa_reporter (BACI): structure, coverage 2000-2024, two_way identity,
    and USA mirror cross-check vs the validated US aggregate.

Read-only. Prints a PASS/FAIL/FLAG table. Run:
  conda run -n us_china_africa_trade python scripts/50_validate_outputs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import config  # noqa: E402

OUT = config.Paths.output
BENCH = {"US": 72_576_740_427, "China": 295_366_109_606}  # 2024 two-way, Comtrade total line
TOL = 1.0  # dollar tolerance for internal identities

results: list[tuple[str, str, str]] = []  # (status, check, note)


def record(ok: bool | None, check: str, note: str = "") -> None:
    status = "PASS" if ok else ("FAIL" if ok is False else "FLAG")
    results.append((status, check, note))


def main() -> None:
    agg = pd.read_csv(OUT / "us_china_africa_trade_aggregate_long.csv")
    alt = pd.read_csv(OUT / "us_china_africa_trade_alt_categories_long.csv")
    byc = pd.read_csv(OUT / "us_china_africa_trade_by_country_long.csv")

    reporters = ["US", "China"]
    main_cats = ["agricultural goods", "minerals & metals", "apparel", "other manufactured goods"]

    # ---- 1. External benchmark: 2024 two-way ----------------------------------
    row24 = agg[(agg["Year"] == 2024) & (agg["flow"] == "two_way")].iloc[0]
    for r in reporters:
        actual = row24[f"{r}_Africa_total"]
        delta = actual - BENCH[r]
        record(abs(delta) < TOL, f"2024 two-way {r} == benchmark",
               f"expected {BENCH[r]:,.0f}, got {actual:,.0f}, delta {delta:+,.0f}")

    # ---- 2. two_way = imports + exports (aggregate) ---------------------------
    value_cols = [c for c in agg.columns if c not in ("Year", "flow")]
    piv = agg.pivot_table(index="Year", columns="flow", values=value_cols, aggfunc="first")
    bad = 0
    for yr in agg["Year"].unique():
        for c in value_cols:
            imp, exp, tw = (piv.loc[yr, (c, f)] for f in ("imports", "exports", "two_way"))
            if pd.isna(imp) and pd.isna(exp):
                continue
            if abs((imp + exp) - tw) > TOL:
                bad += 1
    record(bad == 0, "aggregate two_way == imports+exports", f"{bad} mismatches > ${TOL:g}")

    # ---- 3. Africa_total == sector cats + unspecified -------------------------
    bad = 0
    for r in reporters:
        cat_cols = [f"{r} {c}" for c in main_cats] + [f"{r} unspecified (HS 99)"]
        for _, row in agg.iterrows():
            tot = row[f"{r}_Africa_total"]
            s = row[cat_cols].sum(skipna=True)
            if pd.isna(tot) and row[cat_cols].isna().all():
                continue
            if abs(s - tot) > TOL:
                bad += 1
    record(bad == 0, "Africa_total == 4 cats + unspecified", f"{bad} mismatches > ${TOL:g}")

    # ---- 4. World_ex_Africa_total reconstructed from raw reporter_world -------
    cache = config.Paths.raw_data / "reporter_world"
    world = {}
    for f in cache.glob("*.json"):
        rep, yr, flow = f.stem.split("_")
        body = json.loads(f.read_text(encoding="utf-8"))
        tot = sum((row.get("primaryValue") or 0.0)
                  for row in (body.get("data") or [])
                  if row.get("partner2Code", 0) in (0, None))
        world[(rep, int(yr), flow)] = tot
    bad, checked = 0, 0
    for r in reporters:
        for _, row in agg.iterrows():
            if row["flow"] == "two_way":
                continue
            wea = row[f"{r}_World_ex_Africa_total"]
            afr = row[f"{r}_Africa_total"]
            wt = world.get((r, int(row["Year"]), row["flow"]))
            if pd.isna(wea) or wt is None:
                continue
            checked += 1
            if abs((wt - afr) - wea) > max(TOL, abs(wea) * 1e-9):
                bad += 1
    record(bad == 0, "World_ex_Africa_total == world(raw) - Africa_total",
           f"{checked} cells checked, {bad} mismatches")
    # magnitude sanity: full-world two-way 2024 (Africa + World_ex_Africa)
    for r in reporters:
        wea = row24[f"{r}_World_ex_Africa_total"]
        full = wea + row24[f"{r}_Africa_total"]
        record(None, f"2024 total goods trade {r} (sanity)", f"${full/1e12:,.2f}T two-way")

    # ---- 5. No negatives ------------------------------------------------------
    neg = 0
    for df, cols in ((agg, value_cols),
                     (alt, [c for c in alt.columns if c not in ("Year", "flow")]),
                     (byc, ["value_usd"])):
        neg += int((df[cols] < 0).sum().sum())
    record(neg == 0, "no negative USD values", f"{neg} negatives across agg/alt/by_country")

    # ---- 6. Cross-scheme: alt 7 sectors == main 4 sectors ---------------------
    # (main & alt share an "apparel" column name, so compare via keyed lookups,
    #  not a merge that would suffix the collision.)
    bad = 0
    agg_k = agg.set_index(["Year", "flow"])
    alt_k = alt.set_index(["Year", "flow"])
    for r in reporters:
        alt_sect = [f"{r} raw agrifood", f"{r} processed agrifood", f"{r} energy minerals",
                    f"{r} unrefined minerals", f"{r} refined minerals",
                    f"{r} apparel", f"{r} other manufactured"]
        main_sect = [f"{r} {c}" for c in main_cats]
        for key in agg_k.index:
            a = agg_k.loc[key, main_sect].sum(skipna=True)
            b = alt_k.loc[key, alt_sect].sum(skipna=True)
            if agg_k.loc[key, main_sect].isna().all() and alt_k.loc[key, alt_sect].isna().all():
                continue
            if abs(a - b) > TOL:
                bad += 1
    record(bad == 0, "alt 7-sector sum == main 4-sector sum", f"{bad} mismatches > ${TOL:g}")

    # ---- 7. by_country sums to aggregate categories ---------------------------
    bad = 0
    g = (byc.groupby(["Year", "flow", "reporter", "category"], as_index=False)["value_usd"]
         .sum())
    for r in reporters:
        for c in main_cats:
            sub = g[(g["reporter"] == r) & (g["category"] == c)]
            for _, row in sub.iterrows():
                agg_row = agg[(agg["Year"] == row["Year"]) & (agg["flow"] == row["flow"])]
                if agg_row.empty:
                    continue
                target = agg_row.iloc[0][f"{r} {c}"]
                if pd.isna(target):
                    continue
                if abs(row["value_usd"] - target) > TOL:
                    bad += 1
    record(bad == 0, "by_country sum == aggregate categories", f"{bad} mismatches > ${TOL:g}")

    # ---- 8. Duplicate keys ----------------------------------------------------
    dup_agg = agg.duplicated(["Year", "flow"]).sum()
    dup_byc = byc.duplicated(["Year", "flow", "reporter", "country_iso3", "category"]).sum()
    record(dup_agg == 0 and dup_byc == 0, "no duplicate keys",
           f"agg dups={dup_agg}, by_country dups={dup_byc}")

    # ---- 9. Coverage: years, reporters, countries -----------------------------
    yrs = sorted(agg["Year"].unique())
    record(yrs == list(range(2000, 2026)), "years 2000-2025 present", f"{len(yrs)} years")
    n_countries = byc["country_iso3"].nunique()
    record(n_countries == 54, "54 AU countries in by_country", f"{n_countries} countries")

    # China 2025 blank / US 2025 present
    c25 = agg[(agg["Year"] == 2025)]["China_Africa_total"].isna().all()
    u25 = agg[(agg["Year"] == 2025)]["US_Africa_total"].notna().all()
    record(bool(c25), "China 2025 blank (not yet published)", "expected blank")
    record(bool(u25), "US 2025 present", "expected populated")

    # ---- 10. africa_reporter (BACI, reconciled) -------------------------------
    ar_path = OUT / "us_china_africa_trade_africa_reporter_long.csv"
    if not ar_path.exists():
        record(False, "africa_reporter present", "long CSV missing (run 44_africa_reporter.py)")
    else:
        ar = pd.read_csv(ar_path)
        regions = {"USA", "China", "N_America_ex_US", "S_America", "Asia_ex_China",
                   "Europe", "Oceania", "Intra_Africa", "Other_residual (nes)"}
        # structure
        ok_struct = (set(ar["partner_region"]) == regions
                     and set(ar["flow"]) == {"imports", "exports", "two_way"}
                     and set(ar["category"]) == set(main_cats)
                     and set(ar["source"].unique()) == {"baci_reconciled"})
        record(ok_struct, "africa_reporter structure (BACI)",
               f"{ar['partner_region'].nunique()} regions, {ar['category'].nunique()} cats, "
               f"source={list(ar['source'].unique())}")
        # years 2000-2024 (BACI has no 2025)
        yrs_ar = sorted(ar["Year"].unique())
        record(yrs_ar == list(range(2000, 2025)), "africa_reporter years 2000-2024",
               f"{len(yrs_ar)} years")
        # no negatives, no duplicate keys
        record(int((ar["value_usd"] < 0).sum()) == 0, "africa_reporter no negatives",
               f"{int((ar['value_usd'] < 0).sum())} negatives")
        dup_ar = ar.duplicated(["Year", "flow", "partner_region", "category"]).sum()
        record(dup_ar == 0, "africa_reporter no duplicate keys", f"{dup_ar} dups")
        # two_way == imports + exports
        arp = ar.pivot_table(index=["Year", "partner_region", "category"],
                             columns="flow", values="value_usd", aggfunc="first")
        tw_bad = int((arp["two_way"] - (arp["imports"].fillna(0) + arp["exports"].fillna(0)))
                     .abs().gt(TOL).sum())
        record(tw_bad == 0, "africa_reporter two_way == imports+exports", f"{tw_bad} mismatches")
        # USA mirror cross-check against the validated US aggregate
        us = agg.set_index(["Year", "flow"])["US_Africa_total"]
        for fl_ar, fl_us, lo, hi in [("exports", "imports", 0.90, 1.10),
                                     ("imports", "exports", 0.90, 1.50)]:
            a = ar[(ar["partner_region"] == "USA") & (ar["flow"] == fl_ar)].groupby("Year")["value_usd"].sum()
            ratios = [a[y] / us[(y, fl_us)] for y in a.index if (y, fl_us) in us.index and us[(y, fl_us)]]
            med = pd.Series(ratios).median()
            record(lo <= med <= hi, f"africa_reporter USA {fl_ar} ~ US {fl_us} (mirror)",
                   f"ratio median {med:.3f}, range {min(ratios):.3f}-{max(ratios):.3f} (band {lo}-{hi})")

        # ---- 10b. External benchmarks on the partner-share data ---------------
        ar_tw = ar[ar["flow"] == "two_way"]
        reg_tw = (ar_tw.groupby(["Year", "partner_region"], observed=True)["value_usd"]
                       .sum().unstack("partner_region"))

        # (a) China cross-source: BACI China two_way 2024 vs the validated Comtrade
        #     China total. BACI is FOB-reconciled and excludes HS 99, so it should
        #     sit a few % BELOW the Comtrade gross total (CIF import leg + ch99).
        chn_baci_24 = float(reg_tw.loc[2024, "China"])
        ratio_chn = chn_baci_24 / BENCH["China"]
        record(0.85 <= ratio_chn <= 1.02,
               "africa_reporter China 2024 ~ Comtrade China total (cross-source)",
               f"BACI ${chn_baci_24/1e9:,.1f}B vs Comtrade ${BENCH['China']/1e9:,.1f}B, "
               f"ratio {ratio_chn:.3f} (band 0.85-1.02; BACI FOB, no ch99)")

        # (b) Africa total merchandise trade (X+M) 2024 vs UNCTAD (~$1.4-1.5T).
        afr_total_24 = float(reg_tw.loc[2024].sum())
        record(1.20e12 <= afr_total_24 <= 1.70e12,
               "africa_reporter 2024 Africa total trade ~ UNCTAD",
               f"${afr_total_24/1e12:,.2f}T two-way (UNCTAD Africa merch. X+M ~$1.4-1.5T; band 1.2-1.7T)")

        # (c) Structural: China is Africa's largest single-country partner
        #     (China two_way > USA two_way) every year from 2010 on.
        yrs_ge10 = [y for y in reg_tw.index if y >= 2010]
        n_chn = sum(reg_tw.loc[y, "China"] > reg_tw.loc[y, "USA"] for y in yrs_ge10)
        record(n_chn == len(yrs_ge10),
               "China > USA every year >= 2010 (largest single-country partner)",
               f"{n_chn}/{len(yrs_ge10)} years")

        # (d) Structural: Europe is Africa's largest partner region every year.
        n_eur = sum(reg_tw.loc[y].idxmax() == "Europe" for y in reg_tw.index)
        record(n_eur == len(reg_tw.index), "Europe is Africa's largest region every year",
               f"{n_eur}/{len(reg_tw.index)} years")

        # ---- 10c. extra-Africa share file (publication-safe partner shares) ----
        ex_path = OUT / "us_china_africa_trade_africa_reporter_totals_wide_pct_extra_africa.csv"
        if not ex_path.exists():
            record(False, "extra-Africa share file present", "missing (run 44_africa_reporter.py)")
        else:
            ex = pd.read_csv(ex_path)
            no_intra = "Intra_Africa" not in ex.columns
            reg_c = [c for c in ex.columns if c not in ("Year", "flow")]
            sums = ex[reg_c].sum(axis=1)
            sums_ok = bool(((sums - 100).abs() <= 0.05).all())
            record(no_intra and sums_ok,
                   "extra-Africa shares sum to 100, no Intra_Africa column",
                   f"rows={len(ex)}, max|sum-100|={float((sums - 100).abs().max()):.3f}, "
                   f"intra_excluded={no_intra}")

    # ---- report ---------------------------------------------------------------
    width = max(len(c) for _, c, _ in results)
    print("\n" + "=" * 78)
    print("VALIDATION — us_china_africa_trade outputs (on disk)")
    print("=" * 78)
    for status, check, note in results:
        print(f"[{status:4}] {check:<{width}}  {note}")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")
    n_flag = sum(1 for s, _, _ in results if s == "FLAG")
    print("=" * 78)
    print(f"{len(results)} checks — {n_fail} FAIL, {n_flag} FLAG, "
          f"{len(results) - n_fail - n_flag} PASS")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
