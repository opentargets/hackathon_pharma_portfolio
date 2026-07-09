"""Map Amgen's raw fetched pipeline rows onto the shared PipelineRecord schema.

Pass 2 of the two-pass workflow. Reads raw_pipeline.json (written by
scrape_pipeline.py), applies the field-mapping decisions documented in
log.md, and writes amgen_pipeline.parquet.
"""

import html as html_module
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.amgenpipeline.com/"
EXTRACTION_DATE = date(2026, 7, 9)

PHASE_LABEL_MAP = {
    "1": Phase.PHASE_1,
    "2": Phase.PHASE_2,
    "3": Phase.PHASE_3,
}

TRADEMARK_RE = re.compile(r"®|™")
# Internal Amgen/legacy code, e.g. "AMG 732", "ABP 206", "HZN-280" -- real
# alternate identifiers containing a digit, unlike a bare INN/generic name.
CODE_RE = re.compile(r"\d")
BIOSIMILAR_RE = re.compile(r"Investigational biosimilar to (.+?)\s*\(([^)]+)\)", re.I)


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = html_module.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_name(molecule_name: str, molecule_code: str) -> tuple[str, list[str], list[str]]:
    """Split (molecule_name, molecule_code) into (asset_name, synonyms, others_extra).

    Four patterns in the source (see log.md):
    - Brand name + generic in the code field, e.g. "Aimovig(R)" / "(erenumab-aooe)".
    - Brand name + generic embedded in the name itself (code field empty),
      e.g. "LUMAKRAS(R)(sotorasib)".
    - Investigational biosimilar code with no generic yet, code field
      describes the reference product, e.g. "ABP 206" /
      "(Investigational biosimilar to OPDIVO(R) (nivolumab))".
    - Bare generic/INN name or internal code, optionally with an old code
      noted "formerly X", e.g. "Maridebart Cafraglutide (MariTide, formerly
      AMG 133)", "AMG 732 (formerly HZN-280)", "Daxdilimab".
    Per user decision: generic/INN name or compound code is asset_name;
    brand name and any old code/nickname go to synonyms.
    """
    name = clean(molecule_name)
    code = clean(molecule_code)
    others_extra = []

    if code.lower().startswith("(investigational biosimilar"):
        m = BIOSIMILAR_RE.search(code)
        if m:
            brand, generic = m.group(1).strip(), m.group(2).strip()
            brand = TRADEMARK_RE.sub("", brand).strip()
            others_extra.append(f"Biosimilar of: {generic} ({brand})")
        return name, [], others_extra

    if code.startswith("(") and code.endswith(")"):
        # Brand name (outer) + generic (inner code field).
        return code[1:-1].strip(), [name.rstrip("®™").strip()], others_extra

    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", name)
    if not m:
        # Bare code or INN name, nothing else on the page.
        return (name if CODE_RE.search(name) else name.lower()), [], others_extra

    prefix, inner = m.group(1).strip(), m.group(2).strip()
    if TRADEMARK_RE.search(name):
        # Brand name (outer) + generic embedded directly in the name.
        return inner, [TRADEMARK_RE.sub("", prefix).strip()], others_extra

    # No brand: prefix is the generic/INN name or internal code; inner is
    # "OLD_CODE" or "NICKNAME, formerly OLD_CODE".
    synonyms = []
    if "," in inner:
        nickname, rest = (p.strip() for p in inner.split(",", 1))
        synonyms.append(nickname)
        inner = rest
    if inner.lower().startswith("formerly"):
        synonyms.append(inner[len("formerly"):].strip())
    else:
        synonyms.append(inner)

    asset_name = prefix if CODE_RE.search(prefix) else prefix.lower()
    return asset_name, synonyms, others_extra


def split_description(description: str) -> tuple[str, str | None]:
    """Split off an "ADDITIONAL CLINICAL STUDIES" clause embedded inline in
    Description (distinct from the separate AdditionalInformation field;
    present for 4 molecules -- BLINCYTO, IMDELLTRA, LUMAKRAS, XALURITAMIG).
    """
    desc = clean(description)
    if "ADDITIONAL CLINICAL STUDIES" in desc:
        main, extra = desc.split("ADDITIONAL CLINICAL STUDIES", 1)
        return main.strip(), extra.strip()
    return desc, None


def extract_moa(desc: str) -> str | None:
    m = re.match(r"^.*?investigational biosimilar to .+?\([^)]+\),\s*which is (?:a|an)\s+(.+?)\.", desc, re.I)
    if m:
        return m.group(1).strip()
    m = re.match(r"^.*?\bis\s+(?:a|an)\s+(.+?)\.\s", desc)
    if m:
        return m.group(1).strip()
    m = re.match(r"^.*?\bis\s+(?:a|an)\s+(.+?)\s+being investigated", desc)
    if m:
        return m.group(1).strip()
    return None


def build_record(row: dict) -> PipelineRecord:
    asset_name, synonyms, others = split_name(row["molecule_name"], row["molecule_code"])

    indications = row["indications"] or []
    indication = clean(indications[0]["HtmlString"]) if indications else None
    others += [f"Indication tag: {clean(i['HtmlString'])}" for i in indications[1:]]

    desc, additional_clinical_studies = split_description(row["description"])
    notes_parts = []
    if additional_clinical_studies:
        notes_parts.append(f"Additional clinical studies: {additional_clinical_studies}")
    if clean(row["additional_information"]):
        notes_parts.append(clean(row["additional_information"]))

    return PipelineRecord(
        company="Amgen",
        asset_name=asset_name,
        synonyms=synonyms or None,
        mechanism_of_action=extract_moa(desc),
        therapeutic_area=clean(row["therapeutic_area"]["HtmlString"]),
        indication=indication,
        phase=PHASE_LABEL_MAP[row["phase"]["HtmlString"]],
        trial_id=None,
        source_url=SOURCE_URL,
        extraction_date=EXTRACTION_DATE,
        modality=clean(row["modality"]) or None,
        notes=" ".join(notes_parts) or None,
        others=others or None,
    )


def main():
    raw_rows = json.loads((HERE / "raw_pipeline.json").read_text())
    records = [build_record(row) for row in raw_rows]

    df = pd.DataFrame([r.model_dump() for r in records])
    out_path = HERE / "amgen_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
