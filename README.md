# us_china_africa_trade

US and China merchandise trade with Africa, 2000–2025 — built for ONE.org
advocacy (US/Canada policy audiences).

Two questions, two sources:

1. **How much do the US and China trade with Africa?** — from **UN Comtrade**,
   with the US and China as reporters, 2000–2025.
2. **What share of Africa's own trade goes to the US, China, the EU, etc.?** —
   from **CEPII BACI** (reconciled bilateral trade), 2000–2024, with a raw
   Comtrade-mirror build as a cross-check.

All values are nominal USD at the HS 2-digit (chapter) level, for the
**54 African Union member states**.

## Scope & conventions

- **Reporters:** US (Comtrade M49 `842`) and China (`156`, mainland only).
- **Partners:** the 54 AU member states (fixed ISO3 + M49 list in `scripts/config.py`).
- **Flows:** imports, exports, and derived two-way (imports + exports).
- **Category schemes** (all HS chapters 01–97 partitioned; see `config.py`):
  - Main 4-bucket: agricultural / minerals & metals / apparel / other manufactured.
  - Alt 7-bucket: raw vs processed agrifood, energy vs critical minerals,
    precious metals & stones, apparel, other manufactured.
- **Three views:**
  1. Aggregate — Africa totalled, plus each reporter's World-excluding-Africa total.
  2. By-country — per AU member.
  3. Africa-as-reporter — Africa's trade split across an 8-region partition
     of the world (US, China, EU, intra-Africa, etc.), with an explicit residual line.

## Why BACI for the Africa-as-reporter view

African countries' own Comtrade import reports record goods by **country of
origin**, which overstated trade with hubs like the US by roughly 2× and failed
a mirror check against US-reported data. BACI reconciles importer and exporter
reports into one bilateral figure, which fixes this for every partner region.
BACI lags about 1.5 years, so this view stops at **2024**.

`48_africa_reporter_comtrade.py` rebuilds the extra-Africa shares from Comtrade
mirror data (each partner's reports, flipped) as an independent check. It is
raw (no CIF/FOB harmonisation), so expect region cells ~5–15% off BACI.

## Pipeline

```
# Comtrade (US & China as reporters)
python scripts/10_fetch_comtrade.py           # raw Comtrade cells -> raw_data/ (resumable, never overwrites)
python scripts/20_aggregate.py                # tidy long tables -> interim/
python scripts/25_totals.py                   # Africa and World-ex-Africa totals

# Africa-as-reporter (BACI) — see the environment note below
python scripts/12_fetch_baci.py               # stream BACI, keep Africa rows -> raw_data/baci/
python scripts/44_africa_reporter.py          # 8-region tables (long + wide + shares)
python scripts/49_baci_by_country_alt.py      # per-country alt categories, BACI version

# Optional Comtrade-mirror cross-check
python scripts/11_enum_mirror_reporters.py    # list the non-African reporters
python scripts/13_fetch_comtrade_batched.py   # batched mirror pull (~52 calls)
python scripts/48_africa_reporter_comtrade.py  # mirror-based extra-Africa shares

# Outputs
python scripts/30_build_outputs.py            # final CSVs + Excel workbook -> output/
python scripts/40_reshape_flourish.py         # Flourish-ready shapes
python scripts/41_reshape_by_country_wide.py
python scripts/43_reshape_alt_by_country.py
python scripts/46_build_category_definitions_doc.py
python scripts/47_us_country_per_category.py  # top-7 AU partners per category

# Validation
python scripts/50_validate_outputs.py         # PASS/FAIL table on the files in output/
```

## Validation

`50_validate_outputs.py` re-checks the files in `output/` (read-only):

- 2024 two-way totals against external benchmarks (US $72.58B, China $295.37B).
- World-excluding-Africa totals rebuilt from raw data and matched to the dollar.
- Identities: two-way = imports + exports; categories sum to the Africa total;
  alt 7-bucket sum = main 4-bucket sum; countries sum to the aggregate.
- No negatives, no duplicate keys, full year and reporter coverage.
- Africa-as-reporter: structure, 2000–2024 coverage, and a US mirror cross-check.

## Outputs (`output/`)

| File | What it is |
|---|---|
| `us_china_africa_trade.xlsx` | Combined workbook, with a README sheet |
| `*_aggregate_long/wide.csv` | Africa totals by year, flow, reporter, main 4 categories |
| `*_alt_categories_long/wide.csv` | Same, alt 7 categories |
| `*_by_country_long/wide.csv`, `*_by_country_categories.csv` | Per AU member |
| `*_by_country_alt_categories.csv` | Per AU member, alt 7 categories (Comtrade) |
| `*_by_country_alt_categories_baci.csv` | Same, from BACI (2000–2024) |
| `*_us_by_country_alt_categories.csv` | US-only version |
| `*_africa_reporter_*.csv` | Africa-as-reporter, 8 regions (BACI). For partner shares use `*_totals_wide_pct_extra_africa.csv` |
| `*_africa_reporter_comtrade_*.csv` | Comtrade-mirror cross-check |
| `us_country_per_category.csv` | Top-7 AU partners of the US per category and year |
| `external_reference_2025.csv` | Hand-sourced 2025 totals (US Census, China GACC) with sources |
| `*_category_definitions.docx` | HS chapter → category definitions |
| `flourish/` | Chart-ready CSVs for Flourish |

## Caveats

- **2025 is provisional.** Comtrade annual data for 2025 lags to ~mid-2026.
- **Intra-Africa two-way shares double-count** intra-African trade; use the
  `_extra_africa` share files for headline partner shares.
- **HS chapter 99** (unspecified) is kept in Comtrade totals but not in BACI,
  which has no chapter 99.

## Setup

**API key.** Create a `.env` in the project root (never commit it):

```
COMETRADE_API_KEY=your_comtrade_primary_key
COMETRADE_SECONDARY_KEY=your_comtrade_secondary_key   # optional
```

Get a key from https://comtradedeveloper.un.org/ . See `.env.example`.

**Environment.** Conda (recommended on Windows, for TLS):

```
conda env create -f environment.yml
conda run -n us_china_africa_trade python scripts/10_fetch_comtrade.py
```

A uv lockfile (`uv.lock`) is also provided. On a network with TLS interception,
the fetchers use the OS trust store.

`12_fetch_baci.py` additionally needs `bblocks-data-importers` and `truststore`,
which are not in `environment.yml`; run it from an environment that has them.

## Notes

- `raw_data/` (~16 GB of raw Comtrade JSON and BACI slices) and `interim/` are
  gitignored — regenerate them from the scripts. Only `output/` is committed.
- Codes are strings; M49 partner codes are zero-padded to 3 digits.

## License

MIT — see `LICENSE`.
