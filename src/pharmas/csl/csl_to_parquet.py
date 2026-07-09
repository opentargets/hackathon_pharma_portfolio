"""Map CSL's raw scraped pipeline rows onto the shared PipelineRecord schema.

Pass 2 of the two-pass workflow. Reads raw_pipeline.json (written by
scrape_pipeline.py), applies the field-mapping decisions documented in
log.md, and writes csl_pipeline.parquet.
"""

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.csl.com/research-and-development/product-pipeline"
EXTRACTION_DATE = date(2026, 7, 9)

PHASE_LABEL_MAP = {
    "Phase I": Phase.PHASE_1,
    "Phase II": Phase.PHASE_2,
    "Phase III": Phase.PHASE_3,
    # CSL's own site doesn't distinguish pre-approval filings from already
    # -marketed products (e.g. FLUCELVAX, VELTASSA) within this bucket, and
    # the schema has no separate "Marketed"/"Approved" value -- confirmed
    # with user to map the whole bucket to REGISTERED (2026-07-09).
    "Registration / Post Registration": Phase.REGISTERED,
}

# Tier 1: explicit treatment/prevention/protection/use connector phrases.
# Checked in order of leftmost match in the source sentence (re.search finds
# the earliest position across all alternatives), so ordering within the
# alternation doesn't matter for rows with only one connector.
MOA_INDICATION_CONNECTORS_TIER1 = re.compile(
    r"\b(?:"
    r"indicated for treatment of"
    r"|for the potential treatment of"
    r"|for potential treatment of"
    r"|for the treatment of"
    r"|for treatment of"
    r"|for the potential prevention of"
    r"|for the prevention of"
    r"|for the potential use in"
    r"|used for the control of"
    r"|for protection against"
    r"|to treat"
    r"|for prophylactic use in"
    r")\b",
    re.IGNORECASE,
)

# Tier 2: fallback connectors, only tried if tier 1 finds nothing (catches
# looser phrasing like ZEMAIRA's "...therapy in adults with A1-PI deficiency").
MOA_INDICATION_CONNECTORS_TIER2 = re.compile(
    r"\b(?:in adults with|in patients with)\b", re.IGNORECASE
)

# Rows where neither tier finds a connector -- the free text has no
# identifiable MoA/indication boundary (verified by eye, see log.md). For
# these, mechanism_of_action stays null and the whole sentence goes to
# indication, per the fallback approved by the user (2026-07-09).
NO_CONNECTOR_ASSET_NAMES = {
    "VMX-C001 rFX (FXa Inhibitor Bypass)*",
    "TS23 Anti-α2AP mAb (sPE)*",
    "Horizon 2 Ig Yield",
    "KOSTAIVE®sa-mRNA Vaccine (COVID)",
    "CSL403 (aTIVc) Adjuvanted Cell-based Trivalent Influenza Vaccine",
}

# The two `*`-marked assets are explained by the page's own footnote (not
# attached to the pipeline items themselves -- see scrape_pipeline.py).
CODEVELOPMENT_FOOTNOTE = (
    "Co-development project; partner owned asset with exclusive option "
    "rights held by CSL (per CSL pipeline page footnote)."
)


def split_moa_indication(content: str) -> tuple[str | None, str]:
    """Split a free-text blurb into (mechanism_of_action, indication).

    Returns (None, content) unchanged when no connector phrase is found.
    """
    m = MOA_INDICATION_CONNECTORS_TIER1.search(content)
    if m is None:
        m = MOA_INDICATION_CONNECTORS_TIER2.search(content)
    if m is None:
        return None, content.strip().rstrip(".")

    moa = content[: m.start()].strip().rstrip(",").strip()
    indication = content[m.end() :].strip().rstrip(".")
    return (moa or None), indication


def extract_brand_synonyms(name: str) -> list[str]:
    """Pull out `®`-marked brand tokens (e.g. "HIZENTRA" out of
    "HIZENTRA®(SCIg) 20% Liquid (SID)"), leaving asset_name untouched.

    Handles the dual-brand case ("ZEMAIRA®/RESPREEZA®Alpha 1
    Antitrypsin...") where the same product is marketed under two names.
    """
    if "®" not in name:
        return []
    parts = name.split("®")
    brands = []
    for piece in parts[:-1]:
        brand = piece.lstrip("/").strip()
        if brand:
            brands.append(brand)
    return brands


def build_record(row: dict) -> PipelineRecord:
    name = row["name"]
    content = row["content"] or ""

    synonyms = extract_brand_synonyms(name) or None

    if name in NO_CONNECTOR_ASSET_NAMES:
        mechanism_of_action, indication = None, content.strip().rstrip(".")
    else:
        mechanism_of_action, indication = split_moa_indication(content)

    others = ["Pipeline data current as at: 26 May 2026 (per CSL page footnote)"]
    notes = None
    if name.rstrip().endswith("*"):
        notes = CODEVELOPMENT_FOOTNOTE

    return PipelineRecord(
        company="CSL",
        asset_name=name,
        synonyms=synonyms,
        mechanism_of_action=mechanism_of_action,
        therapeutic_area=row["therapeutic_area"],
        indication=indication,
        phase=PHASE_LABEL_MAP[row["phase_label"]],
        trial_id=None,
        source_url=SOURCE_URL,
        extraction_date=EXTRACTION_DATE,
        notes=notes,
        others=others,
    )


def main():
    raw = json.loads((HERE / "raw_pipeline.json").read_text())
    records = [build_record(row) for row in raw["rows"]]

    df = pd.DataFrame([r.model_dump() for r in records])
    out_path = HERE / "csl_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
