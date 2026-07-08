"""Convert the Sanofi raw pipeline scrape to the unified parquet schema.

Source: https://sanofi.com/en/our-science/our-pipeline
Raw data was produced by scrape_pipeline.py (src/pharmas/sanofi/raw_pipeline.json).
Field-mapping decisions are recorded in src/pharmas/sanofi/log.md.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://sanofi.com/en/our-science/our-pipeline"

PHASE_MAP = {
    "1": Phase.PHASE_1,
    "2": Phase.PHASE_2,
    "3": Phase.PHASE_3,
    "R": Phase.PREREGISTRATION,
}

# "Also known as X" / "formerly known as X" -> synonyms. X is always a single
# compound-code-like token (e.g. "SAR441566", "INBRX-101", "BLU-808") in this
# source, so matching that token shape (rather than "up to the next comma or
# period") avoids swallowing unrelated trailing text like ", in-licensed from
# MAB Discovery". Everything else in Notes/Collaboration stays free text in
# `notes`.
SYNONYM_RE = re.compile(
    r"(?:\s*and)?\s*(?:also|formerly)\s+known\s+as\s+([A-Za-z0-9][\w-]*)", re.IGNORECASE
)


def extract_synonyms_and_leftover(notes_text: str) -> tuple[list[str], str]:
    if not notes_text:
        return [], ""
    synonyms = [m for m in SYNONYM_RE.findall(notes_text)]
    leftover = SYNONYM_RE.sub("", notes_text).strip(" .,;")
    return synonyms, leftover


def build_notes(collaboration: str, notes_leftover: str) -> str | None:
    parts = [p for p in (collaboration, notes_leftover) if p]
    return "; ".join(parts) if parts else None


def convert(json_path: Path, extraction_date: date) -> list[PipelineRecord]:
    rows = json.loads(json_path.read_text())
    records = []
    for row in rows:
        synonyms, notes_leftover = extract_synonyms_and_leftover(row["notes"] or "")
        notes = build_notes(row["collaboration"] or "", notes_leftover)

        others = None
        timeline = row["expected_submission_timeline"]
        if timeline and timeline != "Not available yet":
            others = [f"Expected Submission Timeline: {timeline}"]

        records.append(
            PipelineRecord(
                company="Sanofi",
                asset_name=row["name"].strip(),
                synonyms=synonyms or None,
                mechanism_of_action=row["description"].strip() if row["description"] else None,
                therapeutic_area=row["therapeutic_area"],
                indication=row["indication"].strip(),
                phase=PHASE_MAP[row["phase_badges"][0]],
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=notes,
                others=others,
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=HERE / "raw_pipeline.json", type=Path)
    parser.add_argument("--out", default=HERE / "sanofi_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-08", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.json, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
