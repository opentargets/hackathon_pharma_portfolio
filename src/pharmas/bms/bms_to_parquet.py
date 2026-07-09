"""Map BMS's raw scraped pipeline rows onto the shared PipelineRecord schema.

Pass 2 of the two-pass workflow. Reads raw_pipeline.json (written by
scrape_pipeline.py), applies the field-mapping decisions documented in
log.md, and writes bms_pipeline.parquet.
"""

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.bms.com/research-and-development/pipeline.html"
EXTRACTION_DATE = date(2026, 7, 9)

PHASE_LABEL_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Registration": Phase.PREREGISTRATION,
}

# Trademark symbols on branded compound names, e.g. "REBLOZYL®", "COBENFY™".
TRADEMARK_RE = re.compile(r"[®™]")
# "NAME (parenthetical)" -> captures the two parts separately.
PARENTHETICAL_RE = re.compile(r"^(.*?)\s*\((.*)\)\s*$")
# BMS internal compound code, e.g. "BMS-986528" -- a real alternate
# identifier, unlike a bare target/MoA descriptor such as "Anti-CCR8".
BMS_CODE_RE = re.compile(r"^BMS-\d+$", re.IGNORECASE)
# Trailing footnote asterisk on indication labels -- the footnote text is
# client-JS-rendered and absent from the static HTML, so its meaning is
# unknown; stripped per user decision (see log.md).
TRAILING_ASTERISK_RE = re.compile(r"\*+$")


def split_compound_token(name: str) -> tuple[str, str | None, str | None]:
    """Split a single compound token into (asset_name, synonym, moa_hint).

    Two distinct parenthetical patterns appear in the source, disambiguated
    by the trademark symbol:
    - "REBLOZYL® (luspatercept-aamt)" -- brand(generic): asset_name is the
      generic, brand goes to synonym.
    - "CD19 TCE (BMS-986528)" / "imzokitug (Anti-CCR8)" -- no trademark
      symbol; the outer name is already the real identifier. The
      parenthetical is a real alternate code (matches "BMS-\\d+") -> synonym,
      or a target/MoA descriptor -> moa_hint.
    - "milvexian" -- no parenthetical at all.
    """
    name = name.strip()
    m = PARENTHETICAL_RE.match(name)
    if not m:
        return name, None, None
    outer, inner = m.group(1).strip(), m.group(2).strip()
    if TRADEMARK_RE.search(outer):
        return inner, TRADEMARK_RE.sub("", outer).strip(), None
    if BMS_CODE_RE.match(inner):
        return outer, inner, None
    return outer, None, inner


def build_record_name_fields(
    compound_name: str,
) -> tuple[str, list[str] | None, str | None]:
    """Handle plain, branded, code, and multi-drug combo compound strings.

    Combos are joined with "+" (source uses "+\\n"); each constituent is
    split independently, then rejoined in order.
    """
    parts = [p.strip() for p in compound_name.split("+")]
    asset_names, synonyms, moa_hints = [], [], []
    for part in parts:
        asset_name, synonym, moa_hint = split_compound_token(part)
        asset_names.append(asset_name)
        if synonym:
            synonyms.append(synonym)
        if moa_hint:
            moa_hints.append(moa_hint)
    asset_name = " + ".join(asset_names)
    moa = "; ".join(moa_hints) if moa_hints else None
    return asset_name, (synonyms or None), moa


def build_record(row: dict) -> PipelineRecord:
    asset_name, synonyms, mechanism_of_action = build_record_name_fields(
        row["compound_name"]
    )
    indication = TRAILING_ASTERISK_RE.sub("", row["indication"]).strip()

    others = []
    if row.get("nme_status"):
        others.append(f"NME status: {row['nme_status']}")
    if row.get("research_area"):
        others.append(f"Research area: {row['research_area']}")
    if row.get("registration_status"):
        others.append(f"Registration status: {row['registration_status']}")

    return PipelineRecord(
        company="Bristol Myers Squibb",
        asset_name=asset_name,
        synonyms=synonyms,
        mechanism_of_action=mechanism_of_action,
        therapeutic_area=row["category"],
        indication=indication,
        phase=PHASE_LABEL_MAP[row["phase_label"]],
        trial_id=None,
        source_url=SOURCE_URL,
        extraction_date=EXTRACTION_DATE,
        notes=None,
        others=others or None,
    )


def main():
    raw_rows = json.loads((HERE / "raw_pipeline.json").read_text())
    records = [build_record(row) for row in raw_rows]

    df = pd.DataFrame([r.model_dump() for r in records])
    out_path = HERE / "bms_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
