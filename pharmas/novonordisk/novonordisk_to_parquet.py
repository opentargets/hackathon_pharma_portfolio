"""Convert the Novo Nordisk raw pipeline scrape to the unified parquet schema.

Source: https://www.novonordisk.com/science-and-technology/r-d-pipeline.html
Raw data was produced by scrape_pipeline.py (pharmas/novonordisk/raw_pipeline.json).
Field-mapping decisions are recorded in pharmas/novonordisk/log.md.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.novonordisk.com/science-and-technology/r-d-pipeline.html"

AREA_LABELS = {
    "diabetes": "Diabetes",
    "obesity": "Obesity",
    "rare-blood-disorders": "Rare Blood Disorders",
}

PHASE_MAP = {
    "phase-1": Phase.PHASE_1,
    "phase-2": Phase.PHASE_2,
    "phase-3": Phase.PHASE_3,
    "filed": Phase.PREREGISTRATION,
}

INDICATION_CLAUSE_RE = re.compile(r"\s*for (?:the )?treatment of ([^.]+)", re.IGNORECASE)


def split_indication_moa(description: str, area_label: str, asset_name: str) -> tuple[str, str]:
    """Most rows are 'Indication heading\\nMoA/detail sentence'. A few are a single
    sentence with no heading; for those, pull the indication out of a 'for (the)
    treatment of X' clause if present, else fall back to the therapeutic area.
    A couple of rows have the asset name itself as the heading (source data quirk,
    no real indication authored) -- fall back to the therapeutic area for those too.
    """
    lines = [line.strip().replace("\xa0", " ") for line in description.split("\n") if line.strip()]
    if len(lines) >= 2:
        if lines[0].lower() == asset_name.lower():
            return area_label, " ".join(lines[1:])
        return lines[0], " ".join(lines[1:])

    line = lines[0] if lines else ""
    match = INDICATION_CLAUSE_RE.search(line)
    if match:
        indication = match.group(1).strip().rstrip(".")
        indication = indication[0].upper() + indication[1:]
        moa = (line[: match.start()] + line[match.end() :]).strip().rstrip(".").strip()
        return indication, moa
    return area_label, line


def convert(json_path: Path, extraction_date: date) -> list[PipelineRecord]:
    rows = json.loads(json_path.read_text())
    records = []
    for row in rows:
        area_label = AREA_LABELS[row["area"]]
        asset_name = row["name"].strip()
        indication, moa = split_indication_moa(row["description_text"], area_label, asset_name)
        records.append(
            PipelineRecord(
                company="Novo Nordisk",
                asset_name=asset_name,
                synonyms=None,
                mechanism_of_action=moa or None,
                therapeutic_area=area_label,
                indication=indication,
                phase=PHASE_MAP[row["phase"]],
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=None,
                others=[f"Raw description: {row['description_text']}"],
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=HERE / "raw_pipeline.json", type=Path)
    parser.add_argument("--out", default=HERE / "novonordisk_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-08", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.json, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
