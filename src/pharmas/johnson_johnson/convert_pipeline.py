"""Convert the J&J pipeline (scraped text) to the unified parquet schema.

Source: https://investor.jnj.com/pipeline/development-pipeline/
Scraped via Playwright (bypasses Cloudflare), rendered data extracted as text.
Field-mapping decisions are recorded in src/pharmas/johnson_johnson/log.md.
"""

import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://investor.jnj.com/pipeline/development-pipeline/"

PHASE_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Registration": Phase.PREREGISTRATION,
}


def parse_text(text: str) -> list[dict]:
    """Parse the rendered page text into (asset, indication, phase, TA) entries."""
    lines = [l.strip() for l in text.split("\n")]
    # Remove empty lines, keep only meaningful ones
    meaningful = [l for l in lines if l and len(l) > 2]

    # Find therapeutic area boundaries
    ta_markers = ["Oncology", "Immunology", "Neuroscience", "Select Other Areas"]
    entries = []
    current_ta = None

    # Find where the actual data starts (after "total indications")
    start_idx = 0
    for idx, line in enumerate(meaningful):
        if "total indications" in line:
            start_idx = idx + 1
            break

    # TA names - also cover sub-TA names that appear in Select Other Areas
    ta_markers_all = set(ta_markers)

    i = start_idx
    while i < len(meaningful):
        line = meaningful[i]

        if line.startswith("*This is not a fully exhaustive"):
            break

        if line in ta_markers_all:
            current_ta = line if line != "Select Other Areas" else None
            i += 1
            continue

        # A pipeline entry: asset_name, then indication, then phase
        if i + 2 < len(meaningful):
            asset = line
            indication = meaningful[i + 1]
            phase = meaningful[i + 2]

            if phase in PHASE_MAP and asset != indication:
                entries.append({
                    "asset_name": asset,
                    "indication": indication,
                    "phase_text": phase,
                    "therapeutic_area": current_ta,
                })
                i += 3
                continue

        i += 1

    return entries


def convert(text_path: Path, extraction_date: date) -> list[PipelineRecord]:
    text = text_path.read_text(encoding="utf-8")
    parsed = parse_text(text)
    records = []

    for p in parsed:
        asset_text = p["asset_name"]
        phase = PHASE_MAP[p["phase_text"]]

        # Extract compound code from parenthetical as asset_name
        # Pattern: "BRAND (code)" or just "code" or "name with ®"
        code_match = re.match(r"^.*\(([^)]+)\)$", asset_text)
        if code_match:
            code = code_match.group(1)
            # Clean up the code
            code = code.strip()
            brand = asset_text[:asset_text.find("(")].strip()
            synonyms = [brand] if brand and brand != code else None
            asset_name = code
        else:
            asset_name = asset_text
            synonyms = None

        # Clean therapeutic area
        ta = p["therapeutic_area"]
        if ta == "Select Other Areas":
            # Try to infer more specific TA from context
            ta = None  # Keep as None for now

        records.append(
            PipelineRecord(
                company="Johnson & Johnson",
                asset_name=asset_name,
                synonyms=synonyms,
                mechanism_of_action=None,
                therapeutic_area=ta,
                indication=p["indication"],
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                modality=None,
                notes=None,
            )
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=HERE / "page_text.txt", type=Path)
    parser.add_argument("--out", default=HERE / "jnj_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-09", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.text, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
