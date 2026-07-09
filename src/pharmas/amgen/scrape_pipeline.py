"""Fetch Amgen's pipeline data into raw, unmapped rows.

Pass 1 of the two-pass workflow (fetch raw -> map to schema separately).
No schema mapping happens here.

The pipeline page (https://www.amgenpipeline.com/) is client-rendered: the
static HTML has no data ("Showing 0 results" placeholder). Its own JS
(pipeline-custom.js) loads data via a plain, unauthenticated GET to
https://www.amgenpipeline.com/pipeline/molecule/getjsondata (anti-forgery
token is commented out in the source JS) -- `curl`ing that endpoint directly
returns the full dataset. No browser/Playwright needed.

A quarterly PDF ("Download Pipeline Chart") also exists and covers the same
30 molecules, but its PHASE column is graphical (bar/chart position, not
text) -- confirmed empty via pdfplumber's extract_tables(). The JSON endpoint
is a strict superset (same content plus explicit numeric phase), so it's the
only source used. See log.md.
"""

import json
import urllib.request
from pathlib import Path

URL = "https://www.amgenpipeline.com/pipeline/molecule/getjsondata"
HERE = Path(__file__).parent


def fetch_json() -> dict:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def flatten_rows(data: dict) -> list[dict]:
    """One row per molecule x indication-page, unmapped."""
    rows = []
    for molecule in data["AmgenPiplines"]:
        for page in molecule["Pages"]:
            rows.append(
                {
                    "molecule_name": molecule["MoleculeName"],
                    "molecule_code": molecule.get("MoleculeCode"),
                    "description": page.get("Description"),
                    "additional_information": page.get("AdditionalInformation"),
                    "therapeutic_area": page.get("TherapeuticAreas"),
                    "phase": page.get("Phase"),
                    "indications": page.get("Indications"),
                    "modality": page.get("Modality"),
                }
            )
    return rows


def main():
    data = fetch_json()
    (HERE / "amgen_raw.json").write_text(json.dumps(data, indent=2))

    rows = flatten_rows(data)
    (HERE / "raw_pipeline.json").write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} raw rows to raw_pipeline.json ({len(data['AmgenPiplines'])} molecules)")


if __name__ == "__main__":
    main()
