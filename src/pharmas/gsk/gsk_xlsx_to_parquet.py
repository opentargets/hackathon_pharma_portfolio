"""Convert the GSK pipeline xlsx to the unified parquet schema.

Source: https://www.gsk.com/en-gb/innovation/pipeline#our-pipeline
Field-mapping decisions are recorded in pharmas/gsk/log.md.
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.gsk.com/en-gb/innovation/pipeline#our-pipeline"

PHASE_MAP = {
    "Phase I": Phase.PHASE_1,
    "Phase II": Phase.PHASE_2,
    "Phase III": Phase.PHASE_3,
    "Registration": Phase.PREREGISTRATION,
}

# Only used to build the human-readable `others` extras, keyed by source column name.
EXTRA_COLUMNS = [
    "In-license or other alliance relationship with third party",
    "Footnotes",
    "Reviewed and final",
]


def clean(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def build_synonyms(asset_name: str, generic_name: str, brand_name: str) -> list[str] | None:
    seen = []
    for value in (generic_name, brand_name):
        if value and value != asset_name and value not in seen:
            seen.append(value)
    return seen or None


def build_others(row: pd.Series) -> list[str] | None:
    others = [f"{col}: {clean(row[col])}" for col in EXTRA_COLUMNS if clean(row[col])]
    return others or None


def convert(xlsx_path: Path, extraction_date: date) -> list[PipelineRecord]:
    df = pd.read_excel(xlsx_path)
    records = []
    for _, row in df.iterrows():
        asset_name = clean(row["Compound Number"])
        records.append(
            PipelineRecord(
                company="GSK",
                asset_name=asset_name,
                synonyms=build_synonyms(asset_name, clean(row["INN / Generic Name"]), clean(row["Brand Name"])),
                mechanism_of_action=clean(row["Mode of Action / Vaccine Type"]) or None,
                therapeutic_area=clean(row["Therapeutic Area"]),
                indication=clean(row["Indication"]),
                phase=PHASE_MAP[clean(row["Current Phase"])],
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
    parser.add_argument("--xlsx", default=HERE / "1q2026-pipeline-list.xlsx", type=Path)
    parser.add_argument("--out", default=HERE / "gsk_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-08", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.xlsx, args.extraction_date)
    out_df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    out_df.to_parquet(args.out, index=False)
    print(f"Wrote {len(out_df)} rows to {args.out}")


if __name__ == "__main__":
    main()
