"""Locked configuration for the us_china_africa_trade pipeline.

Every downstream Comtrade pull and aggregation reads its constants from here.
Pinning them down (including the HS 71 placement) prevents re-pulling data later.

Scope is locked to HS 2-digit chapter level, nominal USD, 2000-2025.
See context/03_data_contract.md for output schemas and context/04_decision_log.md
for the reasoning behind category placements.
"""

from pathlib import Path


class Paths:
    """Class to store the paths to the data and output folders."""

    project = Path(__file__).resolve().parent.parent
    raw_data = project / "raw_data"
    output = project / "output"
    scripts = project / "scripts"


# ---------------------------------------------------------------------------
# Years
# ---------------------------------------------------------------------------

# Inclusive range. China 2025 cells are left blank if Comtrade has not
# published yet (handled downstream, not here).
YEAR_RANGE = list(range(2000, 2026))  # 2000..2025


# ---------------------------------------------------------------------------
# Reporters (Comtrade M49 codes, as strings per the data contract)
# ---------------------------------------------------------------------------

# US = 842 and China = 156 are the locked Comtrade codes (see control room).
# 842 is Comtrade's "USA" reporter; 156 is mainland China only (Hong Kong 344
# and Macao 446 are separate reporters and fall under Asia_ex_China).
REPORTERS = {"US": "842", "China": "156"}


# ---------------------------------------------------------------------------
# 54 African Union member states (Comtrade M49 + ISO3)
# ---------------------------------------------------------------------------

# The canonical, fixed list used across every dataset. 54 states = the
# UN-recognised African countries (AU membership excluding Western Sahara,
# which has no Comtrade reporter). Codes are strings; ISO3 is uppercase.
# Sudan uses M49 729 (post-2011 split; South Sudan = 728 separately).
AFRICA_AU_COUNTRIES = {
    # North Africa (6)
    "012": {"iso3": "DZA", "name": "Algeria"},
    "818": {"iso3": "EGY", "name": "Egypt"},
    "434": {"iso3": "LBY", "name": "Libya"},
    "504": {"iso3": "MAR", "name": "Morocco"},
    "729": {"iso3": "SDN", "name": "Sudan"},
    "788": {"iso3": "TUN", "name": "Tunisia"},
    # West Africa (16)
    "204": {"iso3": "BEN", "name": "Benin"},
    "854": {"iso3": "BFA", "name": "Burkina Faso"},
    "132": {"iso3": "CPV", "name": "Cabo Verde"},
    "384": {"iso3": "CIV", "name": "Côte d'Ivoire"},
    "270": {"iso3": "GMB", "name": "Gambia"},
    "288": {"iso3": "GHA", "name": "Ghana"},
    "324": {"iso3": "GIN", "name": "Guinea"},
    "624": {"iso3": "GNB", "name": "Guinea-Bissau"},
    "430": {"iso3": "LBR", "name": "Liberia"},
    "466": {"iso3": "MLI", "name": "Mali"},
    "478": {"iso3": "MRT", "name": "Mauritania"},
    "562": {"iso3": "NER", "name": "Niger"},
    "566": {"iso3": "NGA", "name": "Nigeria"},
    "686": {"iso3": "SEN", "name": "Senegal"},
    "694": {"iso3": "SLE", "name": "Sierra Leone"},
    "768": {"iso3": "TGO", "name": "Togo"},
    # Central Africa (8)
    "120": {"iso3": "CMR", "name": "Cameroon"},
    "140": {"iso3": "CAF", "name": "Central African Republic"},
    "148": {"iso3": "TCD", "name": "Chad"},
    "178": {"iso3": "COG", "name": "Congo"},
    "180": {"iso3": "COD", "name": "Dem. Rep. of the Congo"},
    "226": {"iso3": "GNQ", "name": "Equatorial Guinea"},
    "266": {"iso3": "GAB", "name": "Gabon"},
    "678": {"iso3": "STP", "name": "Sao Tome and Principe"},
    # East Africa (18)
    "108": {"iso3": "BDI", "name": "Burundi"},
    "174": {"iso3": "COM", "name": "Comoros"},
    "262": {"iso3": "DJI", "name": "Djibouti"},
    "232": {"iso3": "ERI", "name": "Eritrea"},
    "231": {"iso3": "ETH", "name": "Ethiopia"},
    "404": {"iso3": "KEN", "name": "Kenya"},
    "450": {"iso3": "MDG", "name": "Madagascar"},
    "454": {"iso3": "MWI", "name": "Malawi"},
    "480": {"iso3": "MUS", "name": "Mauritius"},
    "508": {"iso3": "MOZ", "name": "Mozambique"},
    "646": {"iso3": "RWA", "name": "Rwanda"},
    "690": {"iso3": "SYC", "name": "Seychelles"},
    "706": {"iso3": "SOM", "name": "Somalia"},
    "728": {"iso3": "SSD", "name": "South Sudan"},
    "834": {"iso3": "TZA", "name": "United Rep. of Tanzania"},
    "800": {"iso3": "UGA", "name": "Uganda"},
    "894": {"iso3": "ZMB", "name": "Zambia"},
    "716": {"iso3": "ZWE", "name": "Zimbabwe"},
    # Southern Africa (6)
    "024": {"iso3": "AGO", "name": "Angola"},
    "072": {"iso3": "BWA", "name": "Botswana"},
    "748": {"iso3": "SWZ", "name": "Eswatini"},
    "426": {"iso3": "LSO", "name": "Lesotho"},
    "516": {"iso3": "NAM", "name": "Namibia"},
    "710": {"iso3": "ZAF", "name": "South Africa"},
}

assert len(AFRICA_AU_COUNTRIES) == 54, "AU list must hold exactly 54 members"


# ---------------------------------------------------------------------------
# HS chapter category schemes
# ---------------------------------------------------------------------------
# HS chapters are 2-digit strings, zero-padded ("01".."97"). Chapter 77 is
# reserved/unused in HS and carries no trade; it is harmless wherever it lands.
# HS 71 (pearls, precious/semi-precious stones, precious metals, jewellery,
# coin) is treated as MINERAL — see decision log 2026-06-05. For Africa it is
# overwhelmingly raw gold/diamonds/platinum, an extractive flow, not manufacturing.


def _chapters(*ranges) -> list[str]:
    """Expand (start, end) inclusive pairs into zero-padded 2-digit strings."""
    out: list[str] = []
    for start, end in ranges:
        out.extend(f"{c:02d}" for c in range(start, end + 1))
    return out


# Main 4-bucket scheme (all datasets).
HS_CATEGORY_MAP_MAIN = {
    "agricultural goods": _chapters((1, 24)),
    "mined goods": _chapters((25, 27)) + ["71"],          # HS 71 -> mineral
    "apparel": _chapters((50, 63)),
    "other manufactured goods": _chapters((28, 49), (64, 70), (72, 97)),
}

# Alt 7-bucket scheme (aggregate-Africa outputs only). Was 6 buckets; HS 71 is
# pulled out into its own "precious metals & stones" line rather than folded
# into critical minerals (HS 26 = ores; gold/diamonds are not strategic
# critical minerals) — see decision log 2026-06-05.
HS_CATEGORY_MAP_ALT = {
    "raw agrifood": ["01", "02", "03", "05", "06", "07", "08", "09", "10", "12", "13", "14"],
    "processed agrifood": ["04", "11", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24"],
    "energy minerals": ["27"],
    "critical minerals": ["26"],
    "precious metals & stones": ["71"],
    "apparel": _chapters((50, 63)),
    "other manufactured": ["25"] + _chapters((28, 49), (64, 70), (72, 97)),
}


def _audit_scheme(scheme: dict, label: str) -> None:
    """Every HS chapter 01-97 must appear in exactly one bucket."""
    seen: dict[str, str] = {}
    for cat, chapters in scheme.items():
        for ch in chapters:
            if ch in seen:
                raise ValueError(f"{label}: chapter {ch} in both '{seen[ch]}' and '{cat}'")
            seen[ch] = cat
    expected = {f"{c:02d}" for c in range(1, 98)} - {"77"}  # 77 reserved
    missing = expected - set(seen)
    if missing:
        raise ValueError(f"{label}: chapters not assigned: {sorted(missing)}")


_audit_scheme(HS_CATEGORY_MAP_MAIN, "MAIN")
_audit_scheme(HS_CATEGORY_MAP_ALT, "ALT")


# ---------------------------------------------------------------------------
# Africa-as-reporter: 8-region partner partition
# ---------------------------------------------------------------------------
# The 8 regions partition the world ex-Antarctica into mutually exclusive M49
# code lists. Built from the country_converter (coco) classification table
# (pinned in uv.lock) — NOT hand-typed from memory — so this stays a trustworthy
# locked source of truth. Three judgment calls resolved 2026-06-15 (decision log):
#   1. China = mainland 156 only; Hong Kong (344), Macao (446), Taiwan (490)
#      fall under Asia_ex_China.
#   2. S_America = all of Latin America & Caribbean (South + Central America +
#      Caribbean + Mexico), i.e. coco "America" continent minus "Northern America".
#   3. M49 lists sourced from coco's verified table.
#
# coco gap: Taiwan is absent from coco (neither standard M49 158 nor Comtrade's
# 490). Comtrade reports Taiwan trade under partner code 490 ("Other Asia, nes"),
# so 490 is added to Asia_ex_China explicitly per decision (1).
#
# COMTRADE LEGACY CODE GAP (found 2026-06-17, see 08_debug_log.md):
# coco's table uses standard ISO/M49 numeric codes, but Comtrade reports many
# major partners under its own legacy codes that coco does NOT carry — so they
# fell into no region, leaving ~17% of Africa-reporter trade unregioned (France
# alone = ~$1.08T). The overrides below patch the gap. Identities verified
# against Comtrade's authoritative partnerAreas reference. The big ones:
#   251 France, 699 India, 757 Switzerland, 579 Norway  (standard 250/356/756/578).
#
# Anchors kept for reference / downstream reuse.
PARTNER_REGION_ANCHORS = {
    "USA": ["842"],
    "China": ["156"],
}

# Comtrade-specific partner codes absent from coco's geographic table but that
# are genuine geographic areas, routed to their region here. Verified against
# Comtrade partnerAreas (2026-06-17). 490 = Taiwan ("Other Asia, nes").
_EXTRA_COMTRADE_PARTNER_CODES = {
    "Europe": ["251", "757", "579", "568", "891"],
    # 251 France, 757 Switzerland(+Liechtenstein), 579 Norway,
    # 568 "Other Europe, nes", 891 "Serbia and Montenegro" (…2005).
    "Asia_ex_China": ["490", "699"],          # 490 Taiwan, 699 India.
    "Intra_Africa": ["736", "577"],           # 736 Sudan (…2011), 577 "Other Africa, nes".
    "S_America": ["530", "473"],              # 530 Netherlands Antilles (…2010), 473 "LAIA, nes".
    "Oceania": ["527"],                       # 527 "Oceania, nes".
}

# Comtrade partner codes that are NOT assignable to any of the 8 world regions:
# non-geographic aggregates (Areas/Bunkers/Free Zones/Special/Neutral Zone),
# Antarctica (excluded from the partition by design), and a handful of tiny,
# ambiguous near-Antarctic / multi-region territories (combined < $1B over
# 2000–2025). The africa_reporter aggregation must report these as an explicit
# residual line — NEVER silently drop them and NEVER force them into a region.
# Dominated by 899 "Areas, nes" (~$112B) and 837 "Bunkers" (~$25B). The region
# sums therefore equal the World total MINUS this residual. See 08_debug_log.md.
RESIDUAL_PARTNER_CODES = {
    "899": "Areas, nes",
    "837": "Bunkers",
    "838": "Free Zones",
    "839": "Special Categories",
    "536": "Neutral Zone",
    "010": "Antarctica (excluded by design)",
    "074": "Bouvet Island",
    "637": "North America and Central America, nes",
    "239": "South Georgia and the South Sandwich Islands",
    "334": "Heard Island and McDonald Islands",
    "849": "US Misc. Pacific Isds",
}


def _build_partner_regions() -> dict[str, list[str]]:
    """Derive the 8-region partition from coco's M49 classification.

    USA and China are carved out as singletons; the Americas are split into
    Northern America (ex-US) vs everything else (= Latin America & Caribbean);
    the remaining continents map 1:1. Antarctica is intentionally excluded.
    """
    import country_converter as coco

    d = coco.CountryConverter().data
    d = d[d["UNcode"].notna()]
    m49 = {row.name_short: f"{int(row.UNcode):03d}" for row in d.itertuples()}
    by_continent: dict[str, list[str]] = {}
    northern_america: set[str] = set()
    for row in d.itertuples():
        code = f"{int(row.UNcode):03d}"
        by_continent.setdefault(row.continent, []).append(code)
        if row.UNregion == "Northern America":
            northern_america.add(code)

    america = set(by_continent.get("America", []))
    regions = {
        "USA": ["842"],
        "China": ["156"],
        "N_America_ex_US": sorted(northern_america - {"842"}),
        "S_America": sorted(america - northern_america),
        "Asia_ex_China": sorted(set(by_continent.get("Asia", [])) - {"156"}),
        "Europe": sorted(by_continent.get("Europe", [])),
        "Oceania": sorted(by_continent.get("Oceania", [])),
        "Intra_Africa": sorted(by_continent.get("Africa", [])),
    }
    for region, extra in _EXTRA_COMTRADE_PARTNER_CODES.items():
        regions[region] = sorted(set(regions[region]) | set(extra))
    return regions


def _audit_partition(regions: dict[str, list[str]]) -> None:
    """8 regions, mutually exclusive, every code in exactly one region."""
    if len(regions) != 8:
        raise ValueError(f"partition must have 8 regions, got {len(regions)}")
    seen: dict[str, str] = {}
    for region, codes in regions.items():
        for code in codes:
            if code in seen:
                raise ValueError(f"code {code} in both '{seen[code]}' and '{region}'")
            seen[code] = region


AFRICA_REPORTER_PARTNER_REGIONS = _build_partner_regions()
_audit_partition(AFRICA_REPORTER_PARTNER_REGIONS)
