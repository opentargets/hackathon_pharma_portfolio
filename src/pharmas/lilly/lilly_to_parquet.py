"""Convert Eli Lilly pipeline data (scraped JSON) to the unified parquet schema.

Source: https://lilly.com/science/research-development/pipeline
Raw data captured via Playwright network interception of /v1/cdp-data API.
Field-mapping decisions are recorded in src/pharmas/lilly/log.md.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://lilly.com/science/research-development/pipeline"
RAW_JSON = HERE / "raw_pipeline.json"

# Phase titles from API: ['', 'Phase 1', 'Phase 2', 'Phase 3', 'Regulatory Review', 'Regulatory Approval Achieved']
PHASE_MAP = {
    2: Phase.PHASE_2,
    3: Phase.PHASE_3,
    4: Phase.PREREGISTRATION,
    5: Phase.REGISTERED,
}


def build_ta_map(data: dict) -> dict[int, str]:
    ta_by_id = data.get("therapeutic_area_by_id", {})
    return {int(k): v["title"] for k, v in ta_by_id.items()}


def convert(extraction_date: date) -> list[PipelineRecord]:
    data = json.loads(RAW_JSON.read_text())
    ta_map = build_ta_map(data)
    records = []

    for m in data.get("molecules", []):
        phase_idx = m.get("phase")
        phase = PHASE_MAP.get(phase_idx)
        if phase is None:
            continue

        asset_name = m.get("title", "").strip()
        if not asset_name:
            continue

        indication = (m.get("indication") or "").strip()
        if not indication:
            continue

        ta_id = m.get("therapeutic_area_id")
        therapeutic_area = ta_map.get(ta_id) if ta_id else None

        modality = m.get("modalityTitle") or None
        notes = None

        records.append(
            PipelineRecord(
                company="Eli Lilly",
                asset_name=asset_name,
                synonyms=None,
                mechanism_of_action=None,
                therapeutic_area=therapeutic_area,
                indication=indication,
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                modality=modality,
                notes=notes,
            )
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=RAW_JSON, type=Path)
    parser.add_argument("--out", default=HERE / "lilly_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-09", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
