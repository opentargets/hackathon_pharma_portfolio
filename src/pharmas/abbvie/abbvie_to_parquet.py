"""Convert the AbbVie raw pipeline scrape to the unified parquet schema.

Source: https://www.abbvie.com/science/pipeline.html
Raw data was produced by scrape_pipeline.py (src/pharmas/abbvie/raw_pipeline.json).
Field-mapping decisions are recorded in src/pharmas/abbvie/log.md.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.abbvie.com/science/pipeline.html"

PHARMA_PHASE_MAP = {
    "phase1": Phase.PHASE_1,
    "phase2": Phase.PHASE_2,
    "phase3": Phase.PHASE_3,
    "submitted": Phase.PREREGISTRATION,
    "approved": Phase.REGISTERED,
}

DEVICE_PHASE_MAP = {
    "confirmation": Phase.PHASE_3,
    "approved": Phase.REGISTERED,
}

def clean_target(target: str | None) -> str | None:
    if not target or target == "N / A":
        return None
    return target


def build_notes(asset_name: str) -> str | None:
    # a bare "Generic Name (ABBV-code)" parenthetical isn't a combo (e.g.
    # "Icalcaprant (ABBV-1354)") -- only asset names combining two agents
    # with "+" (e.g. "ABBV-166 (SKYRIZI + Lutikizumab)") are combination
    # therapies.
    return "Combination therapy" if "+" in asset_name else None


NA_REGION_VALUES = {"", "N A", "N / A"}


def build_others(region: str | None) -> list[str] | None:
    if not region or region in NA_REGION_VALUES:
        return None
    region = re.sub(r"\s*,\s*", ", ", region)  # source renders "US , EU" with a stray space before the comma
    return [f"Region: {region}"]


def convert(json_path: Path, extraction_date: date) -> list[PipelineRecord]:
    assets = json.loads(json_path.read_text())
    records = []
    for asset in assets:
        is_device = asset["asset_type"] == "device"
        phase_map = DEVICE_PHASE_MAP if is_device else PHARMA_PHASE_MAP
        modality = "Device" if is_device else asset["data_asset_type"]
        asset_name = asset["data_title"]
        notes = build_notes(asset_name)

        for row in asset["indication_rows"]:
            records.append(
                PipelineRecord(
                    company="AbbVie",
                    asset_name=asset_name,
                    synonyms=None,
                    mechanism_of_action=clean_target(asset["data_asset_target"]),
                    therapeutic_area=asset["data_asset_focus_area"],
                    indication=row["indication"],
                    phase=phase_map[row["phase_status_class"]],
                    trial_id=None,
                    source_url=SOURCE_URL,
                    extraction_date=extraction_date,
                    modality=modality,
                    notes=notes,
                    others=build_others(row["region"]),
                )
            )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=HERE / "raw_pipeline.json", type=Path)
    parser.add_argument("--out", default=HERE / "abbvie_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-08", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.json, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
