"""Map MSD's raw scraped pipeline rows onto the shared PipelineRecord schema.

Pass 2 of the two-pass workflow. Reads raw_pipeline.json (written by
scrape_pipeline.py), applies the field-mapping decisions documented in
log.md, and writes msd_pipeline.parquet.
"""

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.msd.com/research/product-pipeline/"
EXTRACTION_DATE = date(2026, 7, 8)

PHASE_SLUG_MAP = {
    "phase-2": Phase.PHASE_2,
    "phase-3": Phase.PHASE_3,
    "under-review": Phase.PREREGISTRATION,
}

# Trailing/leading trademark and stray punctuation noise seen in data-name /
# data-code (e.g. "KEYTRUDA®", "ENFLONSIA™", "(MK-3475) **", " (MK-1022)").
TRADEMARK_RE = re.compile(r"[®™]|\*\*")
REGION_SUFFIX_RE = re.compile(r"\s*\(((?:US|EU|JPN)(?:,\s*(?:US|EU|JPN))*)\)\s*$")
PHASE_TEXT_REGION_RE = re.compile(r"\(((?:US|EU|JPN)(?:,\s*(?:US|EU|JPN))*)\)")
MOA_LABEL_RE = re.compile(r"^\s*Mechanism of Action\s*:\s*", re.IGNORECASE)
DESCRIPTION_LABEL_RE = re.compile(r"^\s*Description\s*:\s*", re.IGNORECASE)
IS_A_SENTENCE_RE = re.compile(r"[^.]*\bis (?:a|an)\b[^.]*\.")
NCT_RE = re.compile(r"NCT\d+")


def clean_name(text: str) -> str:
    text = TRADEMARK_RE.sub("", text or "")
    text = text.strip().strip("()").strip()
    return text


def split_region(indication: str) -> tuple[str, str | None]:
    """Strip a trailing (US)/(EU)/(JPN) region tag out of an indication title."""
    m = REGION_SUFFIX_RE.search(indication)
    if not m:
        return indication.strip(), None
    return indication[: m.start()].strip(), m.group(1)


def extract_moa(moa_text: str | None) -> tuple[str | None, str | None]:
    """Split a program's free-text blurb into (mechanism_of_action, extra_notes).

    Most programs have an explicit "Mechanism of Action: ..." labelled
    sentence (everything up to the next sentence boundary after the label);
    the rest of the blurb (acquisition/partnering/combination notes) becomes
    extra notes. Two programs (raludotatug deruxtecan, V181) have no label at
    all -- for those, fall back to the first "<X> is a/an ..." sentence, same
    regex approach used for Roche.
    """
    if not moa_text:
        return None, None

    if MOA_LABEL_RE.search(moa_text):
        unlabelled = MOA_LABEL_RE.sub("", moa_text, count=1)
        m = re.match(r"([^.]*\.)\s*(.*)", unlabelled)
        if m:
            return m.group(1).strip(), (m.group(2).strip() or None)
        return unlabelled.strip(), None

    text = DESCRIPTION_LABEL_RE.sub("", moa_text, count=1)
    m = IS_A_SENTENCE_RE.search(text)
    if m:
        moa = m.group(0).strip()
        rest = (text[: m.start()] + text[m.end() :]).strip()
        return moa, (rest or None)
    return None, text.strip() or None


def primary_nct(trial_text: str | None) -> str | None:
    if not trial_text:
        return None
    m = NCT_RE.search(trial_text)
    return m.group(0) if m else None


# MK-3475A's webpage heading correctly reads "KEYTRUDA QLEX" (matching the
# PDF) -- the earlier "KEYTRUDAA" name came from a bug in MSD's own
# `data-name` HTML attribute, fixed at the scrape layer (scrape_pipeline.py
# now reads the visible heading instead). The MoA text's forward-looking
# rename footnote ("to be marketed as KEYTRUDA SC in the EU", not yet in
# effect) is kept as an extra synonym.
MK_3475A_EXTRA_SYNONYMS = ["KEYTRUDA SC"]


def build_record(row: dict) -> PipelineRecord:
    code = clean_name(row.get("data_code", ""))
    asset_name = clean_name(row["data_name"])
    brand = clean_name(row.get("brand", "")) if row.get("brand") else None

    synonyms = []
    if code and code.lower() != asset_name.lower():
        synonyms.append(code)
    if brand and brand.lower() != asset_name.lower() and brand not in synonyms:
        synonyms.append(brand)
    if code == "MK-3475A":
        synonyms.extend(s for s in MK_3475A_EXTRA_SYNONYMS if s not in synonyms)

    others = []
    trial_text = row.get("trial_text")
    if trial_text:
        others.append(f"Trials: {trial_text}")

    if row["source"] == "webpage":
        indication, region = split_region(row["indication_title"] or "")
        if not region and row.get("phase_text"):
            m = PHASE_TEXT_REGION_RE.search(row["phase_text"])
            if m:
                region = m.group(1)
        phase = PHASE_SLUG_MAP[row["phase_slug"]]
        therapeutic_area = (row.get("therapeutic_area") or "").replace("-", " ").title() or None
        mechanism_of_action, extra_notes = extract_moa(row.get("moa_text"))
        notes = extra_notes
    else:  # pdf_approvals
        indication = row["indication_title"]
        region = row.get("region")
        phase = Phase.REGISTERED
        therapeutic_area = (row.get("therapeutic_area") or "").title() or None
        mechanism_of_action = None
        notes = row.get("notes")

    if region:
        others.append(f"Region: {region}")

    return PipelineRecord(
        company="Merck & Co.",
        asset_name=asset_name,
        synonyms=synonyms or None,
        mechanism_of_action=mechanism_of_action,
        therapeutic_area=therapeutic_area,
        indication=indication,
        phase=phase,
        trial_id=primary_nct(trial_text),
        source_url=SOURCE_URL,
        extraction_date=EXTRACTION_DATE,
        notes=notes,
        others=others or None,
    )


def main():
    raw_rows = json.loads((HERE / "raw_pipeline.json").read_text())
    records = [build_record(row) for row in raw_rows]

    df = pd.DataFrame([r.model_dump() for r in records])
    out_path = HERE / "msd_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
