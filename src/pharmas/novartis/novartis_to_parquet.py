"""Convert scraped Novartis pipeline data to the unified parquet schema.

Field-mapping decisions are recorded in src/pharmas/novartis/log.md.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.novartis.com/research-development/novartis-pipeline"
RAW_JSON = HERE / "raw_pipeline.json"

PHASE_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Registration": Phase.PREREGISTRATION,
}


def convert(extraction_date: date) -> list[PipelineRecord]:
    raw = json.loads(RAW_JSON.read_text())

    records = []
    for row in raw:
        phase = PHASE_MAP.get(row["phase"])
        if phase is None:
            continue

        asset_name = row["compound_name"]
        synonyms = None
        generic = row["generic_name"]
        if generic and generic != asset_name:
            # strip ® suffix for clean synonym
            clean = generic.replace("®", "")
            if clean and clean != asset_name:
                synonyms = [clean]

        others = []
        if row["indication_type"]:
            others.append(f"Indication type: {row['indication_type']}")
        if row["filing_date"]:
            others.append(f"Planned filing: {row['filing_date']}")

        records.append(
            PipelineRecord(
                company="Novartis",
                asset_name=asset_name,
                synonyms=synonyms if synonyms else None,
                mechanism_of_action=row["mechanism_of_action"] or None,
                therapeutic_area=row["therapeutic_area"],
                indication=row["indication_name"],
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=None,
                modality=None,
                others=others if others else None,
            )
        )

    return records


def main() -> None:
    extraction_date = date(2026, 7, 9)
    records = convert(extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    out_path = HERE / "novartis_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()