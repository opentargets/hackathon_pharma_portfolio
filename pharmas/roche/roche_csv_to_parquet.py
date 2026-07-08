"""Convert the Roche pipeline CSV to the unified parquet schema.

Source: https://www.roche.com/solutions/pipeline
Field-mapping decisions are recorded in pharmas/roche/log.md.
"""

import argparse
import csv
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.roche.com/solutions/pipeline"

PHASE_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Filed": Phase.PREREGISTRATION,
    "Approved": Phase.REGISTERED,
}

# Only used to build the human-readable `others` extras, keyed by CSV column name.
EXTRA_COLUMNS = ["Trade name", "Project type", "Partner", "Managed by", "Filing date", "Combination"]


def extract_moa(description: str) -> str | None:
    """Pull the first sentence stating what the compound *is* (its MoA), e.g.
    '...is a bispecific antibody...'. Returns None if no such sentence exists.
    """
    if not description:
        return None
    for sentence in re.split(r"(?<=\.)\s+", description.strip()):
        if re.search(r"\bis (a|an)\b", sentence):
            return sentence.strip()
    return None


def build_synonyms(asset_name: str, generic_name: str, trade_name: str) -> list[str] | None:
    seen = []
    for value in (generic_name, trade_name):
        value = value.strip()
        if value and value != asset_name and value not in seen:
            seen.append(value)
    return seen or None


def build_others(row: dict) -> list[str] | None:
    others = [f"{col}: {row[col].strip()}" for col in EXTRA_COLUMNS if row[col].strip()]
    return others or None


def convert(csv_path: Path, extraction_date: date) -> list[PipelineRecord]:
    records = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            asset_name = row["Compound"].strip()
            records.append(
                PipelineRecord(
                    company="Roche",
                    asset_name=asset_name,
                    synonyms=build_synonyms(asset_name, row["Generic Name"], row["Trade name"]),
                    mechanism_of_action=extract_moa(row["Description"]),
                    therapeutic_area=row["Therapeutic area"].strip(),
                    indication=row["Indication"].strip(),
                    phase=PHASE_MAP[row["Phase"].strip()],
                    trial_id=None,
                    source_url=SOURCE_URL,
                    extraction_date=extraction_date,
                    notes=None,
                    others=build_others(row),
                )
            )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=HERE / "Roche_Pipeline_Final_2026-07-08.csv", type=Path)
    parser.add_argument("--out", default=HERE / "roche_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-08", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.csv, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
