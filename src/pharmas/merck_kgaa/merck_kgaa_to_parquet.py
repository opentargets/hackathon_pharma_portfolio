"""Map Merck KGaA's pipeline data onto the shared PipelineRecord schema.

Two sources merged (both confirmed with the user, see log.md and GitHub
issue #33):
- `merck_kgaa_data.js`: the pipeline widget's own data file
  (`pipelineData = [...]`, fetched directly via plain curl -- no
  click-loop/Playwright needed, see log.md), 10 rows across 3 therapeutic
  areas.
- `merck_kgaa_pipeline_2026-05-21.pdf`: Merck's own chart PDF, same 10
  compound/indication pairs, adding footnote prose (license deals,
  regulatory status, patient-subgroup detail) not present in the JSON's
  `description` field. Footnote numbers don't match between the two
  sources (confirmed mismatch), so footnotes are joined by asset
  name/indication rather than by number.
"""

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
WEBPAGE_SOURCE_URL = "https://www.merckgroup.com/en/research/healthcare-pipeline.html"
PDF_SOURCE_URL = (
    "https://www.merckgroup.com/content/dam/web/corporate/non-images/"
    "business-specifics/healthcare/global/Healthcare-Pipeline-EN.pdf"
)
EXTRACTION_DATE = date(2026, 7, 9)

PHASE_MAP = {
    "1": Phase.PHASE_1,
    "2": Phase.PHASE_2,
    "3": Phase.PHASE_3,
    "4": Phase.PREREGISTRATION,
}

# title1 is always "Name (parenthetical)" or a bare name -- the parenthetical
# is kept verbatim as mechanism_of_action even where it also carries modality
# wording (e.g. "anti-CEACAM5 Antibody drug conjugate"), per user decision.
TRAILING_PAREN_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)$")
SUP_TAG_RE = re.compile(r"<sup>[^<]*</sup>")

# PDF footnote prose, hand-transcribed from merck_kgaa_pipeline_2026-05-21.pdf
# and matched to JSON rows by asset name + indication (not by footnote
# number -- the two sources' superscript numbering doesn't match, see
# log.md). Keyed on (asset_name, indication) exactly as produced below.
PDF_FOOTNOTES = {
    ("pimicotinib", "Tenosynovial giant cell tumor (TGCT)"): (
        "PDF footnote: Merck KGaA entered a license agreement with Abbisko "
        "Therapeutics Co. Ltd, Shanghai, China, holding worldwide "
        "commercialization rights for pimicotinib. On 12 January 2026, the "
        "U.S. FDA accepted the new drug application (NDA) for pimicotinib "
        "as a systemic treatment for patients with TGCT."
    ),
    ("precemtabart tocentecan", "Colorectal Cancer 3L"): (
        "PDF footnote: Including other phase 1 activities in colorectal "
        "cancer (CRC)."
    ),
    ("cabamiquine", "Malaria"): (
        "PDF footnote: In combination with pyronaridine as chemoprevention "
        "in participants with asymptomatic malaria infection."
    ),
    ("M3554", "Advanced Solid Tumors"): (
        "PDF footnote: Patients with soft tissue sarcoma (STS) and "
        "glioblastoma."
    ),
    ("M5542", "T cell-mediated autoimmune diseases"): (
        "PDF footnote: Study in healthy volunteers."
    ),
    ("cladribine capsules", "Generalized Myasthenia Gravis"): (
        "PDF footnote: Putative mechanism."
    ),
    ("enpatoran", "Lupus Rash"): (
        "PDF footnote: Lupus erythematosus patients with active cutaneous "
        "manifestations with or without systemic disease."
    ),
}

# The one row whose trial-link URL text embeds a genuine NCT number, per
# user decision (all other rows' Merck-internal trial IDs go to `others`
# instead of `trial_id`).
NCT_OVERRIDE = {
    ("M7437", "Advanced Solid Tumors"): "NCT07360314",
}


def clean_indication(title2):
    return SUP_TAG_RE.sub("", title2).strip()


def split_asset_moa(title1):
    m = TRAILING_PAREN_RE.match(title1)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title1.strip(), None


def load_rows():
    raw = (HERE / "merck_kgaa_data.js").read_text(encoding="utf-8").strip()
    raw = re.sub(r"^pipelineData\s*=\s*", "", raw).rstrip(";").strip()
    areas = json.loads(raw)
    rows = []
    for area in areas:
        for row in area["dataRows"]:
            rows.append(row)
    return rows


def build_records():
    records = []
    for row in load_rows():
        title1 = SUP_TAG_RE.sub("", row["title1"]).strip()
        asset_name, moa = split_asset_moa(title1)
        indication = clean_indication(row["title2"])
        key = (asset_name, indication)

        others = []
        origin = {"internal": "Internally Derived", "external": "Externally Derived"}.get(
            row.get("asset")
        )
        if origin:
            others.append(f"Origin: {origin}")
        if row.get("year"):
            others.append(f"Year: {row['year']}")
        if row.get("phasetext"):
            others.append(
                f"Sub-phase: {row['phasetext']} (per widget legend, e.g. dose "
                "escalation/expansion and signal seeking)"
            )

        trial_id = NCT_OVERRIDE.get(key)
        for i in range(1, 7):
            link_text = row.get(f"link{i}text")
            link_url = row.get(f"link{i}URL")
            if link_url:
                others.append(f"Clinical trial: {link_text or 'link'} - {link_url}")

        notes = PDF_FOOTNOTES.get(key)

        records.append(
            PipelineRecord(
                company="Merck KGaA",
                asset_name=asset_name,
                mechanism_of_action=moa,
                therapeutic_area=row["type"],
                indication=indication,
                phase=PHASE_MAP[row["phase"]],
                trial_id=trial_id,
                source_url=WEBPAGE_SOURCE_URL,
                extraction_date=EXTRACTION_DATE,
                modality=row.get("entity") or None,
                notes=notes,
                others=others or None,
            )
        )
    return records


def main():
    records = build_records()
    df = pd.DataFrame([r.model_dump() for r in records])
    df["phase"] = df["phase"].apply(lambda p: p.value if isinstance(p, Phase) else p)
    out_path = HERE / "merck_kgaa_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} records to {out_path}")


if __name__ == "__main__":
    main()
