"""Build a Word document defining the main + alt HS category schemes.

Definitions mirror context/03_data_contract.md (the schema authority). Output:
output/us_china_africa_trade_category_definitions.docx
Run: conda run -n us_china_africa_trade python scripts/46_build_category_definitions_doc.py
"""

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from config import Paths

DEST = Paths.output / "us_china_africa_trade_category_definitions.docx"

MAIN = [
    ("Agricultural goods", "01–24",
     "All food and farm products: live animals, meat, fish, dairy/eggs, vegetables, "
     "fruit & nuts, coffee/tea/spices, cereals, oilseeds, fats & oils, and prepared "
     "foods, beverages, spirits and tobacco."),
    ("Minerals & metals", "25, 26, 27, 71, 72, 74–81",
     "The full extractive/metals value chain: salt/stone/cement (25), metal ores, slag & "
     "ash (26), mineral fuels — oil, gas, coal (27), pearls, precious stones & metals incl. "
     "gold, diamonds, platinum (71), AND refined base metals — copper incl. cathodes (74), "
     "cobalt/tantalum/tungsten (81), iron/steel & ferroalloys (72), aluminium, nickel, lead, "
     "zinc, tin (75, 76, 78–80). Refined metals were moved here from manufacturing (2026-09-07)."),
    ("Apparel (wide)", "50–63",
     "Textiles and clothing in the broad sense: silk, wool, cotton and man-made fibres, "
     "knitted and woven garments, and made-up textile articles."),
    ("Other manufactured goods", "28–49, 64–70, 73, 77, 82–97",
     "All remaining manufactures: chemicals, plastics & rubber, leather, wood, paper, "
     "footwear, glass & ceramics, articles of base metal (iron/steel articles 73, tools 82, "
     "misc 83), machinery, electronics, vehicles, and instruments. Excludes the refined base "
     "metals (72, 74–81), which are now in Minerals & metals."),
]

ALT = [
    ("Raw agrifood", "01, 02, 03, 05, 06, 07, 08, 09, 10, 12, 13, 14",
     "Unprocessed/primary agricultural products: live animals, meat, fish, live plants, "
     "vegetables, fruit & nuts, coffee/tea/spices, cereals, oilseeds, and gums."),
    ("Processed agrifood", "04, 11, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24",
     "Processed and prepared foods: dairy/eggs/honey, milling products, fats & oils, "
     "prepared meat/fish, sugar, cocoa, cereal preparations, prepared fruit & vegetables, "
     "beverages & spirits, food residues/animal feed, and tobacco."),
    ("Energy minerals", "27",
     "HS chapter 27 — mineral fuels and oils: crude and refined petroleum, natural gas, "
     "coal, coke, bitumen and mineral waxes. Effectively fossil fuels; for Africa, "
     "dominated by crude oil. (Oil cannot be separated from gas/coal at the 2-digit level.)"),
    ("Unrefined minerals", "26",
     "HS chapter 26 — ores, slag and ash: metal ores and concentrates (iron, copper, "
     "manganese, cobalt, aluminium/bauxite, chromium, etc.) — minerals BEFORE smelting or "
     "refining. Renamed from 'critical minerals' (this is the whole ores chapter, not a "
     "curated strategic list). Pairs with Refined minerals to show Africa's value-addition."),
    ("Refined minerals", "71, 72, 74–81",
     "Refined / semi-processed metals and precious minerals: refined copper incl. cathodes "
     "(74), cobalt/tantalum/tungsten (81), iron/steel & ferroalloys (72), aluminium, nickel, "
     "lead, zinc, tin (75, 76, 78–80), and precious metals & stones — gold, platinum, "
     "diamonds (71). The refined counterpart to Unrefined minerals; for Africa dominated by "
     "copper cathodes (DRC/Zambia) and gold/platinum (South Africa)."),
    ("Apparel (wide)", "50–63",
     "Same as the main scheme: textiles and clothing — silk, wool, cotton and man-made "
     "fibres, knitted/woven garments, and made-up textile articles."),
    ("Other manufactured", "25, 28–49, 64–70, 73, 77, 82–97",
     "All remaining manufactures plus salt/stone/cement (25): chemicals, plastics & rubber, "
     "leather, wood, paper, footwear, glass & ceramics, articles of base metal (73/82/83), "
     "machinery, electronics, vehicles, and instruments. Excludes refined base metals "
     "(72, 74–81), which are in Refined minerals."),
]

NOTES = [
    ("Refined metals → minerals (2026-09-07)", "Refined base metals (HS 72, 74–81) — "
     "overwhelmingly refined copper cathodes (74), plus cobalt (81), ferroalloys (72) and "
     "aluminium (76) — were reclassified from 'other manufactured' into the mineral "
     "categories: Minerals & metals (main), and split Unrefined minerals (26, ores) vs "
     "Refined minerals (71 + 72,74–81) in the alt scheme. For African exports this is ~73% "
     "of the old 'other manufactured' bucket. HS 73 (iron/steel articles), 82 (tools) and "
     "83 (misc base-metal articles) are genuine manufactures and stay in 'other manufactured'."),
    ("HS 71 (precious metals & stones)", "Pearls, precious stones, gold and platinum (HS 71) "
     "are treated as a mineral/extractive flow: in Minerals & metals (main) and folded into "
     "Refined minerals (alt). For US/China–Africa flows it is overwhelmingly refined gold and "
     "platinum. Caveat: HS 71 also holds rough diamonds (unrefined) and a little worked "
     "jewellery/coin, which cannot be separated at the 2-digit level."),
    ("Chapter 99 (unspecified)", "HS chapter 99 (“commodities not elsewhere specified”) "
     "is outside the sector schemes and is reported as a separate “unspecified (HS 99)” "
     "line. The sector categories sum to the classified HS 01–97 subtotal; adding the "
     "unspecified line gives the official Comtrade total."),
    ("Classification basis", "All categories are defined at the HS 2-digit chapter level. "
     "Every chapter 01–97 falls into exactly one bucket within each scheme. Values are "
     "nominal USD."),
    ("Where each scheme applies", "The main 4-category scheme is used in every dataset. "
     "The alt 7-category scheme applies only to the aggregate-Africa outputs."),
]


def shade_header(row):
    for cell in row.cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True


def add_table(doc, rows):
    t = doc.add_table(rows=1, cols=3)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Category", "HS chapters", "What it covers"
    shade_header(t.rows[0])
    for cat, ch, desc in rows:
        c = t.add_row().cells
        c[0].text, c[1].text, c[2].text = cat, ch, desc
        c[0].paragraphs[0].runs[0].bold = True
    return t


def main():
    doc = Document()

    title = doc.add_heading("Trade Category Definitions", level=0)
    sub = doc.add_paragraph("US–China–Africa trade pipeline · HS 2-digit chapter level · nominal USD")
    sub.runs[0].italic = True

    doc.add_heading("1. Main category scheme (4 buckets)", level=1)
    doc.add_paragraph("Used in every dataset (aggregate, by-country, Africa-as-reporter).")
    add_table(doc, MAIN)

    doc.add_heading("2. Alternative category scheme (7 buckets)", level=1)
    doc.add_paragraph("Applies to the aggregate-Africa outputs only. Splits the single "
                      "“Minerals & metals” bucket into energy / unrefined / refined, and "
                      "agriculture into raw vs processed.")
    add_table(doc, ALT)

    doc.add_heading("3. Notes & caveats", level=1)
    for head, body in NOTES:
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(f"{head}. ")
        r.bold = True
        p.add_run(body)

    doc.add_paragraph()
    src = doc.add_paragraph("Source: UN Comtrade, Harmonized System (HS) classification. "
                            "See context/03_data_contract.md and context/04_decision_log.md.")
    src.runs[0].font.size = Pt(9)
    src.runs[0].italic = True

    doc.save(DEST)
    print(f"Wrote {DEST}")


if __name__ == "__main__":
    main()
