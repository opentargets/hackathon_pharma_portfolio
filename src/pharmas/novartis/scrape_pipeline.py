"""Scrape Novartis pipeline page (server-rendered Drupal View, paginated).

The pipeline table is in the initial HTML as .pipeline-main-wrapper divs, paginated
across 6 pages. Fields:
  - compound_name (compound code, e.g. "AAA601")
  - generic_name (brand/INN, e.g. "Lutathera®")
  - indication_name (e.g. "Gastroenteropancreatic neuroendocrine tumors")
  - therapeutic_area (1st span in main-second)
  - phase (2nd span: "Phase 1", "Phase 2", "Phase 3", "Registration")
  - filing_date (3rd span, optional: "2026", "≥ 2029", etc.)
  - mechanism_of_action (4th span, optional)
  - indication_type (optional: "Lead Indication", "Supplementary Indication", "New Indication")

No JS interaction needed. No schema mapping yet.
"""

import csv
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).parent
BASE_URL = "https://www.novartis.com/research-development/novartis-pipeline"
OUT_JSON = HERE / "raw_pipeline.json"
OUT_CSV = HERE / "raw_pipeline.csv"
TOTAL_PAGES = 6


def parse_row(li):
    wrapper = li.find("div", class_="pipeline-main-wrapper")
    if not wrapper:
        return None

    compound_name = wrapper.find("div", class_="compound-name")
    compound_name = compound_name.get_text(strip=True) if compound_name else ""

    generic_indication = wrapper.find("div", class_="main-generic-indication")
    generic_name = ""
    indication_name = ""
    if generic_indication:
        gn = generic_indication.find("div", class_="generic-name")
        if gn:
            generic_name = gn.get_text(strip=True)
        ind = generic_indication.find("div", class_="indication-name")
        if ind:
            indication_name = ind.get_text(strip=True)

    spans = wrapper.find_all("span")
    # spans in main-second: TA, phase, [filing_date], [MoA]
    therapeutic_area = spans[0].get_text(strip=True) if len(spans) > 0 else ""
    phase = spans[1].get_text(strip=True) if len(spans) > 1 else ""
    filing_date = ""
    mechanism_of_action = ""
    if len(spans) >= 3:
        third = spans[2].get_text(strip=True)
        if re.match(r"^(≥\s*)?\d{4}$", third):
            filing_date = third
        else:
            mechanism_of_action = third
    if len(spans) >= 4:
        fourth = spans[3].get_text(strip=True)
        if not mechanism_of_action:
            mechanism_of_action = fourth
        else:
            # this shouldn't happen in normal layout
            if not filing_date and re.match(r"^(≥\s*)?\d{4}$", fourth):
                filing_date = fourth

    indication_type = ""
    mi = wrapper.find("div", class_="main-indication")
    if mi:
        indication_type = mi.get_text(strip=True)

    return {
        "compound_name": compound_name,
        "generic_name": generic_name,
        "indication_name": indication_name,
        "therapeutic_area": therapeutic_area,
        "phase": phase,
        "filing_date": filing_date,
        "mechanism_of_action": mechanism_of_action,
        "indication_type": indication_type,
    }


def main():
    all_rows = []
    for page in range(TOTAL_PAGES):
        url = BASE_URL if page == 0 else f"{BASE_URL}?page={page}"
        print(f"Fetching page {page + 1}/{TOTAL_PAGES}: {url}")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("ul li .pipeline-main-wrapper")
        print(f"  Found {len(items)} items")
        for wrapper in items:
            row = parse_row(wrapper.find_parent("li"))
            if row:
                all_rows.append(row)
        time.sleep(0.5)

    print(f"\nTotal rows extracted: {len(all_rows)}")

    with open(OUT_JSON, "w") as f:
        json.dump(all_rows, f, indent=2, ensure_ascii=False)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "compound_name",
                "generic_name",
                "indication_name",
                "therapeutic_area",
                "phase",
                "filing_date",
                "mechanism_of_action",
                "indication_type",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Saved to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()