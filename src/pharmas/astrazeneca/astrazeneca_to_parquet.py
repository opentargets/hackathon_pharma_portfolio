"""Convert the AstraZeneca pipeline webpage to the unified parquet schema.

Source: https://www.astrazeneca.com/our-therapy-areas/pipeline.html
Data is server-rendered static HTML (no JS needed).
Field-mapping decisions are recorded in src/pharmas/astrazeneca/log.md.
"""

import argparse
import html as htmlmod
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.astrazeneca.com/our-therapy-areas/pipeline.html"

# Map section data-labels to canonical therapeutic area names
AREA_MAP = {
    "Oncology": "Oncology",
    "CardiovascularandMetabolicdisease": "Cardiovascular, Renal and Metabolism",
    "Respiratory": "Respiratory & Immunology",
    "RareDisease": "Rare Disease",
    "InfectiousDisease": "Infectious Disease",
}

# Known trial/protocol name suffixes to strip from compound names
# (sorted longest-first so multi-word patterns match before single-word)
_TRIAL_SUFFIXES = [
    "TULIP 1 & TULIP 2 AZALEA", "TULIP 1 &amp; TULIP 2 AZALEA",
    "Hickory (301), Mulberry (305), Chestnut (303)",
    "OBERON TITANIA PROSPERO MIRANDA",
    "NAVIGATOR DIRECTION",
    "EMBARK, JOURNEY",
    "DESTINY-Breast05", "DESTINY-Breast06", "DESTINY-Breast07",
    "DESTINY-Breast09", "DESTINY-Breast11",
    "DESTINY-BTC01", "DESTINY-Endometrial01", "DESTINY-Endometrial02",
    "DESTINY-Gastric04", "DESTINY-Lung04",
    "DESTINY-PanTumor03", "DESTINY-PanTumor02",
    "TROPION-Breast02", "TROPION-Breast03", "TROPION-Breast04",
    "TROPION-Breast05", "TROPION-Lung05",
    "TROPION-Lung07", "TROPION-Lung08", "TROPION-Lung10",
    "TROPION-Lung14", "TROPION-Lung15", "TROPION-Lung17",
    "ARTEMIDE-Biliary01", "ARTEMIDE-Biliary02",
    "ARTEMIDE-Gastric01", "ARTEMIDE-HCC01",
    "ARTEMIDE-Lung02", "ARTEMIDE-Lung03", "ARTEMIDE-Lung04",
    "ARTEMIDE-01",
    "SOUNDTRACK-B", "SOUNDTRACK-D2", "SOUNDTRACK-E", "SOUNDTRACK-F1",
    "CLARITY-Gastric01", "CLARITY-Gastric02",
    "CAPItello-281", "CAPItello-292",
    "EvoPAR-Breast01", "EvoPAR-Prostate01", "EvoPAR-Prostate02",
    "Bluestar-Endometrial01",
    "DepleTTR-CM",
    "PACIFIC-4", "PACIFIC-5", "PACIFIC-8", "PACIFIC-9",
    "EMERALD-1", "EMERALD-2", "EMERALD-3",
    "eVOLVE-01", "eVOLVE-02", "eVOLVE-Cervical", "eVOLVE-HNSCC",
    "eVOLVE-Lung02", "eVOLVE-Meso", "eVOLVE-RCC02",
    "TREVI-OC-01",
    "NeoCOAST-2",
    "MONO-OLA1",
    "SERENA-4", "SERENA-6",
    "CAMBRIA-1", "CAMBRIA-2",
    "DCMRestore",
    "TULIP-SC",
    "ADAURA2",
    "DUO-E",
    "ESCALADE", "AMPLIFY", "ECHO", "AVANZAR", "BEGONIA",
    "SAFFRON", "NeoADAURA", "ORCHARD",
    "HIMALAYA", "POSEIDON", "MATTERHORN",
    "SUPERNOVA",
    "ALACRITY", "AGILE", "AUTUMN", "CONCORD", "ASTERIA",
    "KALOS", "LOGOS", "THARROS", "MANDARA", "NATRON",
    "DAISY", "IRIS", "JASMINE", "LAVENDER",
    "CROSSING", "WAYPOINT",
    "CALYPSO", "PREVAIL", "KOMET", "AWAKE",
    "POTOMAC", "KUNLUN", "VOLGA", "NILE", "NIAGARA",
    "ATLAS", "ATHLOS", "SAMETA", "ARTEMIS", "AZURE",
    "CARES", "TILIA",
    "BaxHTN", "Bax24", "BaxAsia", "BaxPA",
    "CANTOR", "SYRUS",
    "I CAN",
]

_TRIAL_RE = re.compile(
    r"\s+(?:"
    + "|".join(re.escape(s) for s in sorted(_TRIAL_SUFFIXES, key=len, reverse=True))
    + r")(?:\s*\([^)]*\))*$"
)

PHASE_MAP = {
    "Phase I": Phase.PHASE_1,
    "Phase II": Phase.PHASE_2,
    "Phase III": Phase.PHASE_3,
    "LCM Projects": Phase.PHASE_3,
    "Discontinued": Phase.DISCONTINUED,
}

MODALITY_MAP = {
    "Small molecule": "Small Molecule",
    "Large molecule": "Biologic",
    "Combination molecule": "Combination",
}

BRAND_TO_GENERIC = {
    "Imfinzi": "durvalumab",
    "Imjudo": "tremelimumab",
    "Tagrisso": "osimertinib",
    "Datroway": "datopotamab deruxtecan",
    "Enhertu": "trastuzumab deruxtecan",
    "Calquence": "acalabrutinib",
    "Truqap": "capivasertib",
    "Lynparza": "olaparib",
    "Faslodex": "fulvestrant",
    "Orpathys": "savolitinib",
    "Tezspire": "tezepelumab",
    "Saphnelo": "anifrolumab",
    "Fasenra": "benralizumab",
    "Breztri": "budesonide/glycopyrronium/formoterol",
    "Trixeo": "budesonide/glycopyrronium/formoterol",
    "Ultomiris": "ravulizumab",
    "Koselugo": "selumetinib",
    "Wainua": "eplontersen",
    "Kavigale": "narsoplimab",
}

# Compound codes that should map to their known generic/code names
CODE_TO_GENERIC = {
    "AZD0240": None,
    "AZD0516": None,
    "AZD0754": None,
    "AZD2068": None,
    "AZD2284": None,
    "AZD2962": None,
    "AZD3632": None,
    "AZD4360": None,
    "AZD4512": None,
    "AZD4956": None,
    "AZD5492": None,
    "AZD5863": None,
    "AZD6621": None,
    "AZD6750": None,
    "AZD7003": None,
    "AZD8421": None,
    "AZD9750": None,
    "AZD9793": None,
    "AZD0120": None,
    "AZD0305": None,
    "AZD3470": None,
    "AZD9574": None,
    "camizestrant": None,
    "saruparib": "AZD5305",
    "surovatamig": None,
    "volrustomig": None,
    "rilvegostomig": None,
    "tozorakimab": "AZD0449",
    "puxitatug samrotecan": None,
    "sonesitatug vedotin": None,
    "tilatamig samrotecan": None,
    "torvutatug samrotecan": "AZD5335",
    "baxdrostat": None,
    "efzimfotase alfa": None,
    "eneboparatide": "AZP-3601",
    "gefurulimab": None,
    "cliramitug": None,
    "anselamimab": None,
    "atuliflapon": None,
    "elecoglipron": None,
    "opemalirsen": None,
    "balcinrenone/dapagliflozin": None,
    "zibotentan/dapagliflozin": None,
    "baxdrostat/dapagliflozin": None,
    "AZD1043": None,
    "AZD1613": None,
    "AZD1705": None,
    "AZD3974": None,
    "AZD4063": None,
    "AZD4248": None,
    "AZD4954": None,
    "AZD2389": None,
    "AZD4144": None,
    "AZD5462": None,
    "AZD6234": None,
    "AZD9550 + AZD6234": None,
    "AZD0292": None,
    "AZD1163": None,
    "AZD4604": None,
    "AZD5148": None,
    "AZD6793": None,
    "AZD7760": None,
    "AZD7798": None,
    "AZD8630": None,
    "AZD8965": None,
    "AZD6912": None,
    "FPI-2265": None,
    "IPH5201 + Imfinzi": None,
    "NT-112": None,
    "NT-175": None,
    "ALXN2080": None,
    "ALXN2230": None,
    "ALXN1920": None,
    "ALXN2030": None,
    "ALXN2350": None,
    "ALXN2420": None,
    "AZD1390": None,
    "AZD9574": None,
    "AZD0120": None,
    "laroprovstat": None,
    "tarperprumig": None,
}

# Build synonyms mapping: for each known brand/internal code, list alternatives
SYNONYM_MAP: dict[str, list[str]] = {}
for brand, generic in BRAND_TO_GENERIC.items():
    SYNONYM_MAP.setdefault(brand, []).append(generic)
    SYNONYM_MAP.setdefault(generic, []).append(brand)

for code, gen in CODE_TO_GENERIC.items():
    if gen:
        SYNONYM_MAP.setdefault(code, []).append(gen)
        SYNONYM_MAP.setdefault(gen, []).append(code)


def _strip_trial_suffix(name: str) -> str:
    name = name.replace("EnhertuDESTINY-PanTumor02", "Enhertu")
    while True:
        m = _TRIAL_RE.search(name)
        if not m:
            break
        name = name[: m.start()].strip()
        name = name.rstrip("+/-").strip()
    return name.strip()


def _parse_active_section(sec_start: int, sec_end: int, area_name: str, html_str: str) -> list[dict]:
    """Parse active pipeline compounds within one therapeutic area section."""
    rows = []
    sec_html = html_str[sec_start:sec_end]

    phase_headings = list(
        re.finditer(r'<h3 class="pipeline__phase-title">\s*(.*?)\s*</h3>', sec_html)
    )

    for pi, ph in enumerate(phase_headings):
        phase_label = ph.group(1).strip()
        ph_start = ph.start()
        ph_end = (
            phase_headings[pi + 1].start()
            if pi + 1 < len(phase_headings)
            else len(sec_html)
        )
        ph_html = sec_html[ph_start:ph_end]

        compounds = list(
            re.finditer(
                r'<div class="js-pipeline__compound pipeline__compound">'
                r"(.*?)"
                r"</div>\s*</li>",
                ph_html,
                re.DOTALL,
            )
        )

        for cm in compounds:
            block = cm.group(1)
            row = _extract_compound(block, phase_label, area_name)
            if row:
                rows.append(row)

    return rows


def _extract_compound(block: str, phase_fallback: str, area_name: str) -> dict | None:
    """Extract fields from one compound block."""
    name_m = re.search(
        r'<strong class="pipeline__compound-name">\s*(.*?)\s*</strong>',
        block,
        re.DOTALL,
    )
    full_name = name_m.group(1).strip() if name_m else ""

    if not full_name:
        return None

    phase_m = re.search(r"<span>\s*-\s*(.*?)\s*</span>", block, re.DOTALL)
    phase_val = phase_m.group(1).strip() if phase_m else phase_fallback

    details = re.findall(
        r'<li class="pipeline__compound-detail">\s*<strong>(.*?):</strong>\s*(.*?)\s*</li>',
        block,
        re.DOTALL,
    )

    mechanism = ""
    indication = ""
    modality = ""
    for label, value in details:
        lbl = label.strip()
        val = value.strip()
        if "Mechanism" in lbl:
            mechanism = val
        elif "Area under investigation" in lbl:
            indication = val
        elif "Molecule size" in lbl:
            modality = val

    full_name = htmlmod.unescape(full_name)
    asset_name = _strip_trial_suffix(full_name)

    if mechanism == "0":
        mechanism = ""

    synonyms = _get_synonyms(asset_name)

    return {
        "asset_name": asset_name,
        "synonyms": synonyms if synonyms else None,
        "mechanism": mechanism or None,
        "therapeutic_area": area_name,
        "indication": indication,
        "phase_label": phase_val,
        "modality": modality,
        "notes": None,
        "source_url": SOURCE_URL,
    }


def _parse_html(html_str: str) -> list[dict]:
    """Parse the AstraZeneca pipeline HTML into raw row dicts."""
    rows = []

    # --- Find the 5 labeled therapeutic area sections ---
    section_defs = [
        ("Oncology", 115248),
        ("CardiovascularandMetabolicdisease", 353915),
        ("Respiratory", 402609),
        ("RareDisease", 463950),
        ("InfectiousDisease", 501599),
    ]

    # Verify positions still valid; fall back to dynamic discovery if shifted
    positions_ok = all(
        html_str.find(f'data-label="{name}') == pos
        for name, pos in section_defs
    )
    if not positions_ok:
        section_defs = _discover_sections(html_str)

    section_bounds = []
    for i, (name, pos) in enumerate(section_defs):
        if i + 1 < len(section_defs):
            next_start = section_defs[i + 1][1]
            between = html_str[pos:next_start]
            last_close = between.rfind("</section>")
            end_pos = pos + (last_close if last_close >= 0 else len(between)) + 10
        else:
            term_start = html_str.find("pipeline__terminations-region", pos)
            between = html_str[pos:term_start] if term_start >= 0 else html_str[pos:]
            last_close = between.rfind("</section>")
            end_pos = pos + (last_close if last_close >= 0 else len(between)) + 10
        section_bounds.append((pos, end_pos, name))

    for start, end, name in section_bounds:
        area_name = AREA_MAP.get(name, name)
        for row in _parse_active_section(start, end, area_name, html_str):
            rows.append(row)

    # --- Parse "Removed since last quarter" termination section ---
    term_start = html_str.find("pipeline__terminations-region")
    if term_start >= 0:
        term_html = html_str[term_start:]
        # Find the closing </section>
        term_close = term_html.find("</section>")
        if term_close >= 0:
            term_html = term_html[: term_close + 10]

        term_compounds = list(
            re.finditer(
                r'<div class="js-pipeline__compound pipeline__compound">'
                r"(.*?)"
                r"</div>\s*</li>",
                term_html,
                re.DOTALL,
            )
        )

        for cm in term_compounds:
            block = cm.group(1)

            name_m = re.search(
                r'<strong class="pipeline__compound-name">\s*(.*?)\s*</strong>',
                block,
                re.DOTALL,
            )
            full_name = name_m.group(1).strip() if name_m else ""
            if not full_name:
                continue

            full_name = htmlmod.unescape(full_name)
            asset_name = _strip_trial_suffix(full_name)

            # Extract indication from termination entries
            details = re.findall(
                r'<li class="pipeline__compound-detail">\s*<strong>(.*?):</strong>\s*(.*?)\s*</li>',
                block,
                re.DOTALL,
            )
            indication = ""
            for label, value in details:
                lbl = label.strip()
                val = value.strip()
                if "Area under investigation" in lbl:
                    indication = val

            synonyms = _get_synonyms(asset_name)

            rows.append(
                {
                    "asset_name": asset_name,
                    "synonyms": synonyms if synonyms else None,
                    "mechanism": None,
                    "therapeutic_area": None,
                    "indication": indication,
                    "phase_label": "Discontinued",
                    "modality": None,
                    "notes": "Removed since last quarter",
                    "source_url": SOURCE_URL,
                }
            )

    return rows


def _discover_sections(html_str: str) -> list[tuple[str, int]]:
    """Dynamically find pipeline area sections in the HTML."""
    sections = []
    for m in re.finditer(
        r'<section class="pipeline__areas-region[^"]*"[^>]*data-label="([^"]*)"',
        html_str,
    ):
        sections.append((m.group(1), m.start()))
    if not sections:
        raise ValueError("Could not find any pipeline area sections in HTML")
    return sections


def _get_synonyms(asset_name: str) -> list[str] | None:
    """Return known synonyms for an asset name."""
    result = []
    for token in asset_name.replace("+/-", " ").replace("+", " ").split():
        clean_token = token.strip("(),/")
        if clean_token in SYNONYM_MAP:
            for syn in SYNONYM_MAP[clean_token]:
                if syn.lower() != asset_name.lower() and syn not in result:
                    result.append(syn)
    return result if result else None


def convert(html_path: Path, extraction_date: date) -> list[PipelineRecord]:
    html_str = html_path.read_text(encoding="utf-8")
    raw_rows = _parse_html(html_str)

    records = []
    for row in raw_rows:
        phase = PHASE_MAP.get(row["phase_label"])
        if phase is None:
            continue

        modality = MODALITY_MAP.get(row["modality"])

        records.append(
            PipelineRecord(
                company="AstraZeneca",
                asset_name=row["asset_name"],
                synonyms=row["synonyms"],
                mechanism_of_action=row["mechanism"],
                therapeutic_area=row["therapeutic_area"],
                indication=row["indication"],
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=row["notes"],
                modality=modality,
            )
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html",
        default=HERE / "pipeline_page.html",
        type=Path,
        help="Path to the saved pipeline HTML file",
    )
    parser.add_argument(
        "--out",
        default=HERE / "astrazeneca_pipeline.parquet",
        type=Path,
    )
    parser.add_argument(
        "--extraction-date",
        default="2026-07-08",
        type=date.fromisoformat,
    )
    args = parser.parse_args()

    records = convert(args.html, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
