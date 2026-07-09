"""Map Bayer's pipeline data onto the shared PipelineRecord schema.

Two sources merged (both confirmed with the user, see log.md):
- `bayer_page.html`: the live pipeline webpage (server-rendered HTML table,
  fetched via a browser fetcher since bayer.com bot-blocks plain HTTP
  clients), current as of the fetch date -- 30 rows.
- `bayer_pipeline_2026-02-11.pdf`: Bayer's investor-relations pipeline PDF
  (Feb 11, 2026 snapshot), which adds NCT IDs / estimated completion dates /
  study status for most webpage rows, plus 9 rows not present on the
  webpage at all (see PDF_ONLY_RECORDS below).

The webpage table is parsed programmatically (`parse_webpage_table`). The
PDF's richer per-row fields were extracted with pdfplumber (word/curve
coordinates -- the PDF encodes phase as a 3-column grid, not a text label)
and are hand-transcribed here as lookup tables, following the precedent set
by BMS/MSD for small, one-off cross-source enrichments.
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
WEBPAGE_SOURCE_URL = "https://www.bayer.com/en/pharma/development-pipeline"
PDF_SOURCE_URL = (
    "https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-02-11-final-update.pdf"
)
EXTRACTION_DATE = date(2026, 7, 9)
PDF_SNAPSHOT_DATE = "2026-02-11"

PHASE_ROMAN_MAP = {
    "I": Phase.PHASE_1,
    "II": Phase.PHASE_2,
    "III": Phase.PHASE_3,
}

AREA_CODE_MAP = {
    "ONC": "Oncology",
    "CVR": "Cardiovascular / Renal",
    "NRD": "Neurology & Rare Diseases",
    "IM": "Immunology",
    "Others": "Others",
}

# Modality icon alt-text -> normalised modality label. Several spellings/
# suffixes ("_NTE", "Genetic" vs "Gene", a stray "Melecular" typo) refer to
# the same PDF-legend category; unified here.
MODALITY_ALT_MAP = {
    "small molecule": "Small Molecule",
    "Small Molecule": "Small Molecule",
    "Cell Therapy_NTE": "Cell Therapy",
    "gene therapy": "Gene Therapy",
    "Genetic Therapy": "Gene Therapy",
    "Genetic Therapy_NTE": "Gene Therapy",
    "Gene Therapy_NTE": "Gene Therapy",
    "Protein Therapy": "Protein Therapy",
    "Radiotherapy_NTE": "Radionuclide Therapy",
    "imaging agent": "Imaging Agent",
    "Imaging Agent": "Imaging Agent",
    "New Melecular Entity": "New Molecular Entity",
}

# "Name (parenthetical)" -- webpage's Program cell is always either a bare
# name or a name with a single *trailing* parenthetical. Confirmed by
# inspection that this parenthetical is always a MoA/mechanism descriptor,
# never an internal code or "aka" alt-name (those only appear in the PDF) --
# but the split still checks for a code pattern defensively.
TRAILING_PAREN_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)$")
CODE_RE = re.compile(r"^(BAY[- ]?\d+|VVD-?\d+|AB-?\d+)$", re.IGNORECASE)


def parse_webpage_table():
    html = (HERE / "bayer_page.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tab_pipeline")
    rows = table.find("tbody").find_all("tr")

    records = []
    for row in rows:
        cells = row.find_all("td")
        phase_roman = cells[0].get_text(strip=True)
        area_code = cells[1].get_text(strip=True)
        program_cell = " ".join(cells[2].get_text(separator="\n").split("\n")).strip()
        program_cell = re.sub(r"\s+", " ", program_cell)
        indication = " ".join(cells[3].get_text(separator="\n").split("\n")).strip()
        indication = re.sub(r"\s+", " ", indication)
        img = cells[4].find("img")
        modality_alt = img["alt"] if img else None

        name, moa = program_cell, None
        m = TRAILING_PAREN_RE.match(program_cell)
        if m:
            candidate_name, paren = m.group(1).strip(), m.group(2).strip()
            if CODE_RE.match(paren):
                name = candidate_name
                # A bare code with no MoA text goes to synonyms, handled below.
            else:
                name, moa = candidate_name, paren

        records.append(
            {
                "asset_name": name,
                "synonyms": None,
                "mechanism_of_action": moa,
                "therapeutic_area": AREA_CODE_MAP[area_code],
                "indication": indication,
                "phase": PHASE_ROMAN_MAP[phase_roman],
                "modality": MODALITY_ALT_MAP.get(modality_alt, modality_alt),
            }
        )
    return records


# Enrichment for webpage rows, hand-transcribed from the PDF's "Pipeline
# Details" tables (pages 3-6), keyed by (asset_name, indication) exactly as
# produced by parse_webpage_table(). Extracted via pdfplumber word/curve
# coordinates -- see log.md for the extraction method and the two flagged
# uncertainties (marked below).
PDF_ENRICHMENT = {
    # NB: keys use asset_name/indication *after* parse_webpage_table()'s own
    # MoA-parenthetical split, not the raw webpage cell text -- e.g. the raw
    # cell "Inclocibart (Anti-a2AP)" splits to asset_name "Inclocibart" (the
    # "(Anti-a2AP)" goes to mechanism_of_action instead). Two webpage rows
    # (Darolutamide, Sevabertinib 1L) omit the trial acronym the PDF carries
    # in parens -- a source inconsistency (other rows do include it), not a
    # parsing bug; keyed here on the acronym-less text actually on the page.
    ("Darolutamide", "Adjuvant Prostate Cancer"): dict(
        trial_id="NCT04136353", completion="Q1 2028", status="Study ongoing"
    ),
    (
        "Darolutamide",
        "Prostate Cancer with Biochemical Recurrence after Curative Radiotherapy",
    ): dict(trial_id="NCT05794906", completion="Q3 2027", status="Study ongoing"),
    (
        "Sevabertinib",
        "Advanced Non-small Cell Lung Cancer with HER2 Activating Mutations, 1L",
    ): dict(trial_id="NCT06452277", completion="Q4 2027", status="Study ongoing"),
    (
        "Sevabertinib",
        "Metastatic or Unresectable Solid Tumors with HER2-activating Mutations (PanSOHO)",
    ): dict(trial_id="NCT06760819", completion="Q1 2027", status="Study ongoing"),
    ("Finerenone", "Non-diabetic CKD (FIND-CKD)"): dict(
        trial_id="NCT05047263", completion="Q1 2026", status="Study ongoing"
    ),
    # Name mismatch: webpage's newer INN "Umiposgene Parvec" = PDF's older
    # descriptor "Congestive Heart Failure AAV Gene Therapy (AB-1002)" --
    # same GenePHIT trial, same program code AB-1002. See log.md.
    ("Umiposgene Parvec", "Congestive Heart Failure (GenePHIT)"): dict(
        trial_id="NCT05598333", completion="Q4 2026", status="Study ongoing",
        synonym="AB-1002",
    ),
    ("Inclocibart", "Acute Ischemic Stroke; Pulmonary Embolism (SIRIUS)"): dict(
        trial_id="NCT06149520", completion="Q4 2025", status="Study completed",
        synonym="BAY 3018250",
    ),
    ("Nurandociguat", "Chronic Kidney Disease (ALPINE-1)"): dict(
        trial_id="NCT06522997", completion="Q1 2026", status="Study ongoing",
        synonym="BAY 3283142",
    ),
    ("SEMA 3a", "Alport Syndrome (ASSESS)"): dict(
        trial_id="NCT07211685", completion="Q3 2028", status="Study ongoing",
        synonym="BAY 3401016",
    ),
    # Name mismatch: webpage's "Ametefgene Parvec" = PDF's "Parkinson's
    # Disease AAV Gene Therapy (AB-1005)" for REGENERATE-PD.
    ("Ametefgene Parvec", "Parkinson's Disease (REGENERATE-PD)"): dict(
        trial_id="NCT06285643", completion="Q3 2028", status="Study ongoing",
        synonym="AB-1005",
    ),
    ("VVD Keap1 Act", "Advanced Solid Tumors"): dict(
        trial_id="NCT05954312", completion="Q3 2030", status="Study ongoing",
        synonym="VVD-130037", moa="NRF2 Inhibitor",
    ),
    # UNCERTAIN pairing -- flagged in log.md. PDF lists "225Ac-Pelgifatamab"
    # and "225Ac-PSMA-Trillium" as its two Advanced-Prostate-Cancer
    # radiotherapy rows; webpage lists "...Pelgifatamab Mopaxetan" and
    # "...Felivotide Mopaxetan". Pelgifatamab matches directly by stem name;
    # PSMA-Trillium vs Felivotide Mopaxetan is inferred (same phase/
    # indication/modality, no independent name confirmation), not asserted.
    ("Actinium (225Ac) Pelgifatamab Mopaxetan", "Advanced Prostate Cancer"): dict(
        trial_id="NCT06052306", completion="Q2 2027", status="Study ongoing",
        synonym="BAY 3546828",
    ),
    ("SOS1 Inhibitor", "Advanced Solid Cancers"): dict(
        trial_id="NCT06659341", completion="Q3 2027", status="Study ongoing",
        synonym="BAY 3498264",
    ),
    ("PRMT5 Inhibitor", "MTAP-deleted Solid Tumors"): dict(
        trial_id="NCT06914128", completion="Q2 2029", status="Study ongoing",
        synonym="BAY 3713372",
    ),
    ("VVD RAS-PI3K Inhibitor", "Advanced Solid Tumors"): dict(
        trial_id="NCT06804824", completion="Q3 2027", status="Study ongoing",
        synonym="BAY 3674171",
    ),
    ("225Ac-GPC3", "Advanced Liver Cancer"): dict(
        trial_id="NCT06764316", completion="Q3 2030", status="Study ongoing",
        synonym="BAY 3547926",
    ),
    ("VVD WRN Inhibitor", "Advanced Solid Tumors"): dict(
        trial_id="NCT06004245", completion="Q2 2027", status="Study ongoing",
    ),
    ("KRAS G12D Inhibitor", "Advanced Solid Tumors"): dict(
        trial_id="NCT07207707", completion="Q3 2026", status="Study ongoing",
        synonym="BAY 3771249",
    ),
    # Indication wording differs between sources (webpage: "Anti-
    # coagulation", PDF: "Sepsis-Induced Coagulopathy") -- same compound,
    # flagged in log.md, not resolved.
    ("Dual FIIa/Xa Inhibitor", "Anti-coagulation"): dict(
        trial_id="NCT06854640", completion="Q1 2026", status="Study ongoing",
        synonym="BAY 3389934", notes="PDF indication text: 'Sepsis-Induced Coagulopathy'",
    ),
    ("GIRK4 Inhibitor", "Atrial fibrillation"): dict(
        trial_id=None, completion="Q4 2025", status="Study completed",
        synonym="BAY 3670549", notes="PDF Ct.gov Identifier: 'Undisclosed'",
    ),
    ("BAY 3620122", "Vasoplegia"): dict(
        trial_id=None, completion="Q3 2026", status="Study ongoing",
    ),
    ("Ametefgene Parvec", "Multiple System Atrophy"): dict(
        trial_id="NCT04680065", completion="Q3 2026", status="Study ongoing",
        synonym="AB-1005 (aka AAV2-GDNF-MSA)",
    ),
    ("Pompe Disease AAV Gene Therapy", "Pompe Disease"): dict(
        trial_id="NCT07282847", completion="Q3 2028", status="Recruiting",
        synonym="AB-1009 (aka PROGRESS-GT LOPD)",
    ),
    ("LGMD2I/R9 AAV Gene Therapy", "Limb Girdle Muscular Dystrophy"): dict(
        trial_id="NCT05230459", completion="Q4 2028", status="Study ongoing",
        synonym="AB-1003 (aka LION-101)",
        notes="PDF indication text: 'Limb-Girdle Muscular Dystrophy 2i'",
    ),
    ("Mirena", "Endometrial Hyperplasia (SUNFLOWER)"): dict(
        trial_id="NCT06904274", completion="Q2 2027", status="Study ongoing",
    ),
    ("124I-Evuzamitide", "Diagnosis of Cardiac Amyloidosis (REVEAL)"): dict(
        trial_id="NCT06788535", completion="Q1 2026", status="Study ongoing",
    ),
    ("Primary Photoreceptor Diseases Cell Therapy", "Primary Photoreceptor Disease"): dict(
        trial_id="NCT06789445", completion="Q4 2029", status="Study ongoing",
        synonym="BRT-OpCT-001",
    ),
    # Flagged discrepancy: webpage lists this as Phase I, but the PDF's own
    # detail table shows blank ("n/a") for all three phase columns and no
    # NCT ID -- Bayer's PDF itself treats this compound as undisclosed/
    # unconfirmed at this stage, not a scraping error. See log.md.
    ("AT-05 SPECT Tracer", "Diagnosis of Cardiac Amyloidosis"): dict(
        trial_id=None, completion=None, status=None,
        notes="PDF detail table shows 'n/a' for Phase I/II/III and Ct.gov Identifier",
    ),
    ("Bemdaneprocel", "Parkinson's Disease (exPDite-2)"): dict(
        trial_id="NCT06944522", completion="Q1 2027", status="Study ongoing",
    ),
}

# Rows present in the PDF (Feb 11, 2026 snapshot) but absent from the
# current webpage -- hand-transcribed, phase confirmed via the PDF chart's
# column x-position (see log.md). All get a notes flag.
PDF_ONLY_RECORDS = [
    dict(
        asset_name="Finerenone",
        mechanism_of_action="MR Antagonist",
        therapeutic_area="Cardiovascular / Renal",
        indication="Chronic Kidney Disease in Type 1 Diabetes (FINE-ONE)",
        phase=Phase.PHASE_3,
        trial_id="NCT05901831",
        others=["Estimated/Actual Primary Completion: Q3 2025", "Status: Study completed"],
    ),
    dict(
        asset_name="Vericiguat",
        mechanism_of_action="sGC Stimulator",
        therapeutic_area="Cardiovascular / Renal",
        indication="Heart Failure (HFrEF) (VICTOR2)",
        phase=Phase.PHASE_3,
        trial_id="NCT05093933",
        others=["Estimated/Actual Primary Completion: Q4 2024", "Status: Study completed"],
    ),
    dict(
        asset_name="Asundexian",
        mechanism_of_action="FXIa Inhibitor",
        therapeutic_area="Cardiovascular / Renal",
        indication="2° Stroke Prevention (OCEANIC-STROKE)",
        phase=Phase.PHASE_3,
        trial_id="NCT05686070",
        others=[
            "Estimated/Actual Primary Completion: Q4 2025",
            "Status: Study completed",
            "PDF footnote: Conducted by Merck & Co",
        ],
    ),
    dict(
        asset_name="GPR84 Antagonist",
        synonyms=["BAY 3178275"],
        therapeutic_area="Others",
        indication="Diabetic Neuropathic Pain",
        phase=Phase.PHASE_1,
        trial_id=None,
        others=["Estimated/Actual Primary Completion: Q1 2024", "Status: Study completed"],
    ),
    dict(
        asset_name="BAY 2701250",
        therapeutic_area="Others",
        indication="Pulmonary Hypertension",
        phase=Phase.PHASE_1,
        trial_id="NCT06048120",
        others=["Estimated/Actual Primary Completion: Q2 2025", "Status: Study completed"],
    ),
    dict(
        asset_name="Sevabertinib",
        mechanism_of_action="HER2/mEGFR Inhibitor",
        therapeutic_area="Oncology",
        indication="HER2-mut NSCLC 2L (Indication Expansion)",
        phase=Phase.PREREGISTRATION,
        trial_id=None,
        others=["Region: CN, JP", "PDF section: Submissions / Indication Expansion"],
    ),
    dict(
        asset_name="Finerenone",
        mechanism_of_action="MR Antagonist",
        therapeutic_area="Cardiovascular / Renal",
        indication="Heart Failure (HFmrEF/pEF) (Indication Expansion)",
        phase=Phase.PREREGISTRATION,
        trial_id=None,
        others=["Region: EU, CN", "PDF section: Submissions / Indication Expansion"],
    ),
    dict(
        asset_name="Aflibercept 8mg",
        mechanism_of_action="VEGF Inhibitor",
        therapeutic_area="Others",
        indication="Retinal Vein Occlusion",
        phase=Phase.PREREGISTRATION,
        trial_id=None,
        others=["Region: JP, CN", "PDF section: Submissions / New Molecular Entity"],
    ),
    dict(
        asset_name="Gadoquatrane",
        mechanism_of_action="High Relaxivity Contrast Agent",
        therapeutic_area="Others",
        indication="Magnetic Resonance Imaging",
        phase=Phase.PREREGISTRATION,
        trial_id=None,
        others=["Region: US, EU, JP, CN", "PDF section: Submissions / New Molecular Entity"],
    ),
]


def build_records():
    records = []

    for row in parse_webpage_table():
        key = (row["asset_name"], row["indication"])
        enrichment = PDF_ENRICHMENT.get(key)

        others = []
        notes = None
        trial_id = None
        synonyms = None
        moa = row["mechanism_of_action"]

        if enrichment:
            trial_id = enrichment.get("trial_id")
            if enrichment.get("completion"):
                others.append(f"Estimated/Actual Primary Completion: {enrichment['completion']}")
            if enrichment.get("status"):
                others.append(f"Status: {enrichment['status']}")
            if enrichment.get("synonym"):
                synonyms = [enrichment["synonym"]]
            if enrichment.get("moa") and not moa:
                moa = enrichment["moa"]
            notes = enrichment.get("notes")
        else:
            others.append("Not present in PDF pipeline overview (2026-02-11 snapshot)")

        records.append(
            PipelineRecord(
                company="Bayer",
                asset_name=row["asset_name"],
                synonyms=synonyms,
                mechanism_of_action=moa,
                therapeutic_area=row["therapeutic_area"],
                indication=row["indication"],
                phase=row["phase"],
                trial_id=trial_id,
                source_url=WEBPAGE_SOURCE_URL,
                extraction_date=EXTRACTION_DATE,
                modality=row["modality"],
                notes=notes,
                others=others or None,
            )
        )

    for extra in PDF_ONLY_RECORDS:
        others = list(extra.get("others", []))
        others.append(f"PDF-only ({PDF_SNAPSHOT_DATE} snapshot), not present on the {EXTRACTION_DATE.isoformat()} webpage")
        records.append(
            PipelineRecord(
                company="Bayer",
                asset_name=extra["asset_name"],
                synonyms=extra.get("synonyms"),
                mechanism_of_action=extra.get("mechanism_of_action"),
                therapeutic_area=extra["therapeutic_area"],
                indication=extra["indication"],
                phase=extra["phase"],
                trial_id=extra.get("trial_id"),
                source_url=PDF_SOURCE_URL,
                extraction_date=EXTRACTION_DATE,
                others=others,
            )
        )

    return records


def main():
    records = build_records()
    df = pd.DataFrame([r.model_dump() for r in records])
    df["phase"] = df["phase"].apply(lambda p: p.value if isinstance(p, Phase) else p)
    out_path = HERE / "bayer_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} records to {out_path}")


if __name__ == "__main__":
    main()
