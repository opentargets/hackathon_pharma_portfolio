"""Convert the Teva pipeline (static HTML) to the unified parquet schema.

Source: https://tevapharm.com/science/pipeline/
Field-mapping decisions are recorded in src/pharmas/teva/log.md.
"""

import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://tevapharm.com/science/pipeline/"

PHASE_MAP = {
    "Approved": Phase.REGISTERED,
    "Under Regulatory Review": Phase.PREREGISTRATION,
    "Phase 3": Phase.PHASE_3,
    "Phase 2": Phase.PHASE_2,
    "Phase 1": Phase.PHASE_1,
    "Pre-clinical": Phase.PRECLINICAL,
}

# Map color style -> modality
COLOR_MODALITY = {
    "#00567a": "Biosimilar",
    "#00a03b": "Novel Biologic",
    "#00aca8": "Small Molecule",
}

# Tags that are drug type classifiers (not indications)
DRUG_TYPE_TAGS = {"Biosimilars", "Innovative Medicines"}


def fetch_html() -> str:
    resp = requests.get(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def parse_phase_sections(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    records = []

    phase_sections = soup.select("div.pipeline-phase-js")
    for section in phase_sections:
        heading_tag = section.find(["h3", "H3"])
        if not heading_tag:
            continue
        phase_text = heading_tag.get_text(strip=True)
        if phase_text == "Clinical":
            continue

        phase = PHASE_MAP.get(phase_text)
        if phase is None:
            continue

        items = section.select(".vi-accordion-pipeline__item")
        for item in items:
            title_el = item.select_one(".vi-accordion-pipeline__title")
            subtitle_el = item.select_one(".vi-accordion-pipeline__subtitle")
            desc_el = item.select_one(".vi-accordion-pipeline__content p")
            tag_els = item.select(".vi-accordion-pipeline__tag")
            style = item.get("style", "")

            title = title_el.get_text(strip=True) if title_el else ""
            subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""
            description = desc_el.get_text(strip=True) if desc_el else None

            tags = [t.get_text(strip=True) for t in tag_els]

            modality = None
            color_match = re.search(r'--vi-accordion-pipeline-base-color:\s*(#[0-9a-fA-F]+)', style)
            if color_match:
                modality = COLOR_MODALITY.get(color_match.group(1).lower())

            indication_tags = [t for t in tags if t not in DRUG_TYPE_TAGS]

            asset_name = subtitle.strip("()").strip() if subtitle else title
            synonyms = [title] if title and subtitle else None

            if indication_tags:
                for ind_text in indication_tags:
                    # Split multi-indication by comma (e.g. "Ulcerative Colitis, Crohn's Disease")
                    parts = [p.strip() for p in re.split(r',\s*', ind_text) if p.strip()]
                    for part in parts:
                        records.append({
                            "asset_name": asset_name,
                            "synonyms": synonyms,
                            "phase": phase,
                            "indication": part,
                            "modality": modality,
                            "notes": description,
                            "therapeutic_area": None,
                        })
            else:
                records.append({
                    "asset_name": asset_name,
                    "synonyms": synonyms,
                    "phase": phase,
                    "indication": "",
                    "modality": modality,
                    "notes": description,
                    "therapeutic_area": None,
                })

    return records


def convert(html: str, extraction_date: date) -> list[PipelineRecord]:
    parsed = parse_phase_sections(html)
    records = []
    for p in parsed:
        records.append(
            PipelineRecord(
                company="Teva",
                asset_name=p["asset_name"],
                synonyms=p["synonyms"],
                mechanism_of_action=None,
                therapeutic_area=p["therapeutic_area"],
                indication=p["indication"],
                phase=p["phase"],
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                modality=p["modality"],
                notes=p["notes"],
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=HERE / "teva_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-09", type=date.fromisoformat)
    parser.add_argument("--html", type=Path, help="Read HTML from file instead of fetching")
    args = parser.parse_args()

    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        html = fetch_html()

    records = convert(html, args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
