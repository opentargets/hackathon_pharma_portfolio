"""Convert the Gilead pipeline (SXA search API) to the unified parquet schema.

Source: https://gilead.com/science-and-medicine/pipeline
API: https://gilead.com/sxa/search/results/ (Sitecore SXA search, no auth needed)
Field-mapping decisions are recorded in src/pharmas/gilead/log.md.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from html import unescape

import pandas as pd
import requests
from bs4 import BeautifulSoup

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://gilead.com/science-and-medicine/pipeline"

API_URL = "https://gilead.com/sxa/search/results/"
API_PARAMS = {
    "v": "{16E72BF3-7230-403E-BB34-EAE20C26BD0F}",
    "s": "{B5AA5689-719C-4965-8E20-4B67741FF639}",
    "l": "en",
    "p": 100,
    "defaultSortOrder": "Pipeline Therapeutic Areas,Descending",
    "sig": "pipeline",
    "itemid": "{EFC74AF2-1C5C-4D7C-BACD-F20CD4FF35AA}",
    "autoFireSearch": "true",
}

PHASE_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Filed": Phase.PREREGISTRATION,
}


def fetch_api() -> list[dict]:
    resp = requests.get(
        API_URL,
        params=API_PARAMS,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": SOURCE_URL,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["Results"]


def parse_html_snippet(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    therapeutic_area = soup.select_one(".field-therapeuticareaname")
    therapeutic_area = unescape(therapeutic_area.get_text(strip=True)) if therapeutic_area else None

    tag_spans = soup.select(".field-tagname")
    tag_names = [unescape(t.get_text(strip=True)) for t in tag_spans if t.get_text(strip=True)]

    sub_category = tag_names[0] if len(tag_names) > 0 else None
    phase_text = tag_names[1] if len(tag_names) > 1 else None

    compound_name = soup.select_one(".field-headbrandname")
    compound_name = unescape(compound_name.get_text(strip=True)) if compound_name else None

    indication = soup.select_one(".field-potentialindication")
    indication = unescape(indication.get_text(strip=True)) if indication else None

    notes = soup.select_one(".field-notesdetail")
    notes = unescape(notes.get_text(strip=True)) if notes else None

    return {
        "therapeutic_area": therapeutic_area,
        "sub_category": sub_category,
        "phase_text": phase_text,
        "compound_name": compound_name,
        "indication": indication,
        "notes": notes,
    }


def convert(extraction_date: date) -> list[PipelineRecord]:
    results = fetch_api()
    records = []

    for r in results:
        parsed = parse_html_snippet(r["Html"])
        compound_name = parsed["compound_name"]
        if not compound_name:
            continue

        phase_text = parsed["phase_text"]
        if not phase_text:
            continue

        phase = PHASE_MAP.get(phase_text)
        if phase is None:
            if phase_text == "Opt-in Trials":
                phase = Phase.PHASE_3
            else:
                continue

        # Clean asset name: extract code/INN from parenthetical if present
        # e.g. "Lenacapavir (PURPOSE 365)" -> keep as is since PURPOSE is trial name
        # "Axicabtagene ciloleucel (ZUMA-23)" -> same pattern
        # Remove trailing trial names in parens if they're not compound codes
        asset_name = compound_name
        synonyms = None

        indication_text = parsed["indication"]
        if not indication_text and parsed["sub_category"]:
            indication_text = parsed["sub_category"]

        others = []
        if phase_text == "Opt-in Trials":
            others.append(f"Phase_note: {phase_text}")

        records.append(
            PipelineRecord(
                company="Gilead",
                asset_name=asset_name,
                synonyms=synonyms,
                mechanism_of_action=None,
                therapeutic_area=parsed["therapeutic_area"],
                indication=indication_text or "",
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                modality=None,
                notes=parsed["notes"],
                others=others if others else None,
            )
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=HERE / "gilead_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-09", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
