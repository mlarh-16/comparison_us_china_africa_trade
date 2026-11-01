"""Fetch + cache the BACI Africa trade slice for the africa_reporter dataset.

WHY BACI: the Africa-as-reporter numbers cannot come from African countries'
own Comtrade import reports — those are on a country-of-origin basis and over-
state trade with hubs like the US by ~2x (see 05_validation_log.md, 2026-07-31).
BACI (CEPII) reconciles importer + exporter reports into a single bilateral
figure, fixing this uniformly for every partner region.

ENVIRONMENT: run with the canada_africa_trade_story `.venv` (it has
`bblocks-data-importers` + `truststore`); the project conda env does NOT.
    <repo>/../canada_africa_trade_story/.venv/Scripts/python.exe scripts/12_fetch_baci.py

MEMORY: `BACI().get_data()` assembles the whole world panel and OOMs (~2 GB
Arrow alloc). This instead streams the CEPII zip to disk and reads ONE yearly
CSV at a time, filtering to AU-involved rows before anything accumulates.

SSL: CEPII needs the OS trust store — `truststore.inject_into_ssl()` up top.

Outputs (raw_data/baci/ — a NEW raw cache; existing raw_data is untouched):
  baci_africa_slice.csv : year, flow, partner_iso3, hs2, value_usd
      flow = imports (partner->Africa) | exports (Africa->partner);
      value = BACI value (thousand USD, FOB) * 1000, summed across AU members.
  baci_coverage.csv     : year, n_au_present (distinct AU members in BACI)
  baci_country_codes.csv: BACI country_code -> iso3 map (provenance; lets 44
                          name residual codes without re-downloading 2.4 GB)
  baci_provenance.txt    : HS version, source url, release, year span
"""
import truststore
truststore.inject_into_ssl()

import os
import sys
import tempfile
import zipfile
from collections import defaultdict

import requests
import pandas as pd

from bblocks.data_importers.baci.baci import extract_data_links

HS_VERSION = "HS92"              # longest BACI series; spans 2000-2024
YEARS = set(range(2000, 2025))   # 2000..2024 (BACI current release has no 2025)

# 54 AU member ISO3. Mirrors scripts/config.AFRICA_AU_COUNTRIES (kept literal here
# so this file can run in the .venv without importing config, which pulls in coco).
AU_ISO3 = {
    "DZA", "EGY", "LBY", "MAR", "SDN", "TUN", "BEN", "BFA", "CPV", "CIV", "GMB",
    "GHA", "GIN", "GNB", "LBR", "MLI", "MRT", "NER", "NGA", "SEN", "SLE", "TGO",
    "CMR", "CAF", "TCD", "COG", "COD", "GNQ", "GAB", "STP", "BDI", "COM", "DJI",
    "ERI", "ETH", "KEN", "MDG", "MWI", "MUS", "MOZ", "RWA", "SYC", "SOM", "SSD",
    "TZA", "UGA", "ZMB", "ZWE", "AGO", "BWA", "SWZ", "LSO", "NAM", "ZAF",
}

# US + China ISO3 — for the per-AU-member slice (keeps the African-country
# dimension so a BACI per-country x category sheet can be built; filtered to
# these two partners so the file stays small).
USCHINA = {"USA", "CHN"}

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "raw_data", "baci")
OUT_DIR = os.path.abspath(OUT_DIR)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    links = extract_data_links()
    if HS_VERSION not in links:
        sys.exit(f"{HS_VERSION} not available; have {list(links)}")
    url = links[HS_VERSION]
    print(f"HS={HS_VERSION}  url={url}", flush=True)

    # Stream the zip to a temp file (do not hold the whole download in RAM).
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    print("downloading zip ->", tmp.name, flush=True)
    try:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1 << 20):
                tmp.write(chunk)
        tmp.close()
        print(f"downloaded {os.path.getsize(tmp.name) / 1e6:.0f} MB", flush=True)

        zf = zipfile.ZipFile(tmp.name)
        names = zf.namelist()

        # country_code -> iso3 (persist for provenance / residual naming)
        cc_name = next(f for f in names if f.startswith("country_codes"))
        cc = pd.read_csv(zf.open(cc_name))
        code_col = "country_code" if "country_code" in cc.columns else cc.columns[0]
        iso_col = [c for c in cc.columns if "iso3" in c.lower()][0]
        cc[[code_col, iso_col]].to_csv(
            os.path.join(OUT_DIR, "baci_country_codes.csv"), index=False, encoding="utf-8")
        code2iso = dict(zip(cc[code_col].astype(int), cc[iso_col].astype(str).str.upper()))
        au_codes = {c for c, iso in code2iso.items() if iso in AU_ISO3}
        print(f"country_codes: {len(code2iso)} | AU codes matched: {len(au_codes)}", flush=True)

        data_files = sorted(f for f in names
                            if f.startswith(f"BACI_{HS_VERSION}_Y") and f.endswith(".csv"))
        print(f"{len(data_files)} yearly data files", flush=True)

        agg: dict[tuple, float] = defaultdict(float)   # (year, flow, partner_iso3, hs2) -> usd
        # per-AU-member, US/China partners only: (year, flow, au_iso3, partner_iso3, hs2) -> usd
        agg_uschina: dict[tuple, float] = defaultdict(float)
        coverage: dict[int, set] = {}
        for name in data_files:
            yr = int(name.split("_Y")[1][:4])
            if yr not in YEARS:
                continue
            df = pd.read_csv(
                zf.open(name),
                usecols=["t", "i", "j", "k", "v"],
                dtype={"i": "int32", "j": "int32", "k": "string", "v": "float64"},
            )
            df = df[df["i"].isin(au_codes) | df["j"].isin(au_codes)]
            if df.empty:
                continue
            df["hs2"] = df["k"].str.zfill(6).str[:2]
            present = coverage.setdefault(yr, set())

            for side_is_exporter, flow in ((True, "exports"), (False, "imports")):
                au_col, partner_col = ("i", "j") if side_is_exporter else ("j", "i")
                sub = df[df[au_col].isin(au_codes)].copy()
                sub["partner_iso3"] = sub[partner_col].map(code2iso)
                sub["au_iso3"] = sub[au_col].map(code2iso)
                present.update(sub["au_iso3"].dropna())
                g = sub.groupby(["partner_iso3", "hs2"], observed=True)["v"].sum()
                for (partner, hs2), val in g.items():
                    if pd.notna(partner):
                        agg[(yr, flow, partner, hs2)] += float(val) * 1000.0
                # per-AU-member slice, US/China partners only
                uc = sub[sub["partner_iso3"].isin(USCHINA)]
                if not uc.empty:
                    g2 = uc.groupby(["au_iso3", "partner_iso3", "hs2"], observed=True)["v"].sum()
                    for (au, partner, hs2), val in g2.items():
                        if pd.notna(au):
                            agg_uschina[(yr, flow, au, partner, hs2)] += float(val) * 1000.0

            print(f"  {yr}: AU members present = {len(present)}", flush=True)
            del df, sub

        zf.close()
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

    slice_df = pd.DataFrame(
        [{"year": y, "flow": fl, "partner_iso3": p, "hs2": h, "value_usd": v}
         for (y, fl, p, h), v in agg.items()]
    ).sort_values(["year", "flow", "partner_iso3", "hs2"])
    slice_path = os.path.join(OUT_DIR, "baci_africa_slice.csv")
    slice_df.to_csv(slice_path, index=False, encoding="utf-8")

    # per-AU-member US/China slice (for the BACI per-country x category sheet)
    uc_df = pd.DataFrame(
        [{"year": y, "flow": fl, "au_iso3": au, "partner_iso3": p, "hs2": h, "value_usd": v}
         for (y, fl, au, p, h), v in agg_uschina.items()]
    ).sort_values(["year", "flow", "au_iso3", "partner_iso3", "hs2"])
    uc_path = os.path.join(OUT_DIR, "baci_uschina_by_country_slice.csv")
    uc_df.to_csv(uc_path, index=False, encoding="utf-8")
    print(f"wrote {uc_path}: {len(uc_df):,} rows", flush=True)

    cov = pd.DataFrame(
        [{"year": y, "n_au_present": len(s)} for y, s in sorted(coverage.items())])
    cov.to_csv(os.path.join(OUT_DIR, "baci_coverage.csv"), index=False, encoding="utf-8")

    with open(os.path.join(OUT_DIR, "baci_provenance.txt"), "w", encoding="utf-8") as f:
        f.write(f"HS_VERSION={HS_VERSION}\nurl={url}\n")
        f.write(f"years={min(coverage)}-{max(coverage)}\n")
        f.write("value_usd = BACI value (thousand USD, FOB) * 1000; reconciled bilateral.\n")
        f.write("flow imports = partner->Africa; exports = Africa->partner.\n")

    print(f"\nwrote {slice_path}: {len(slice_df):,} rows")
    print(cov.to_string(index=False))


if __name__ == "__main__":
    main()
