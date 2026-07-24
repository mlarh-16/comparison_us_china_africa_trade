# us_china_africa_trade

US and China merchandise trade with Africa, 2000–2025, from **UN Comtrade** —
built for ONE.org advocacy (US/Canada policy audiences).

The pipeline pulls bilateral trade for two reporters (**US** and **China**)
against the **54 African Union member states**, at the HS 2-digit chapter level,
in nominal USD, and reshapes it into tidy tables and a workbook.

## Data source

UN Comtrade API. Requires a free API key — see **Setup** below. HS 2-digit
(chapter) level; nominal USD; `primaryValue`. 2025 is preliminary (Comtrade's
annual data lags to ~mid-2026), and is published separately as `*_PRELIMINARY_*`.

## Scope & conventions

- **Reporters:** US (Comtrade M49 `842`) and China (`156`, mainland only).
- **Partners:** the 54 AU member states (fixed ISO3 + M49 list in `scripts/config.py`).
- **Flows:** imports, exports, and derived two-way (imports + exports).
- **Category schemes** (all HS chapters 01–97 partitioned; see `config.py`):
  - Main 4-bucket: agricultural / mined / apparel / other manufactured.
  - Alt 7-bucket: raw vs processed agrifood, energy vs critical minerals,
    precious metals & stones, apparel, other manufactured.
- **Three views:**
  1. Aggregate — Africa totalled.
  2. By-country — per AU member.
  3. Africa-as-reporter — Africa's own trade split across an 8-region partition
    of the world (US, China, EU, etc.), with an explicit residual line.

## Pipeline

```
python scripts/10_fetch_comtrade.py          # fetch raw Comtrade cells -> raw_data/ (resumable)
python scripts/20_aggregate.py               # tidy long tables -> interim/
python scripts/25_totals.py                  # totals
python scripts/30_build_outputs.py           # final CSVs + Excel workbook -> output/
python scripts/40_reshape_flourish.py        # Flourish-ready shapes
python scripts/41_reshape_by_country_wide.py
python scripts/43_reshape_alt_by_country.py
python scripts/44_preliminary_africa_reporter.py
python scripts/45_reshape_preliminary_wide.py
python scripts/46_build_category_definitions_doc.py
python scripts/47_us_country_per_category.py
```

## Outputs (`output/`)

Aggregate and by-country tables (long + wide), the main 4-cat and alt 7-cat
category breakdowns, per-country category tables, the Africa-as-reporter
8-region preliminary tables, Flourish-ready CSVs, a category-definitions
document, and a combined Excel workbook.

## Setup

**API key.** Create a `.env` in the project root (never commit it):

```
COMETRADE_API_KEY=your_comtrade_primary_key
COMETRADE_SECONDARY_KEY=your_comtrade_secondary_key   # optional
```

Get a key from https://comtradedeveloper.un.org/ . See `.env.example`.

**Environment.** Conda (recommended on this Windows setup, for TLS):

```
conda env create -f environment.yml
conda run -n us_china_africa_trade python scripts/10_fetch_comtrade.py
```

A uv lockfile (`uv.lock`) is also provided. On a network with TLS interception,
the fetcher uses the OS trust store.

## Notes

- `raw_data/` (~13 GB of raw Comtrade JSON) and `interim/` are gitignored —
  regenerate them from the scripts. Only `output/` is committed.
- Codes are strings; M49 partner codes are zero-padded to 3 digits.
