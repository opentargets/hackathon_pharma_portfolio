"""Scrape BMS's pipeline page into raw, unmapped rows.

Pass 1 of the two-pass workflow (scrape raw -> map to schema separately).
No schema mapping happens here.

The pipeline page (https://www.bms.com/research-and-development/pipeline.html)
turned out to be fully static: `curl`ing it returns the complete dataset
already embedded as HTML-entity-escaped JSON inside a hidden
`<div id="pipeline-data">`. No browser/Playwright needed. Checked for a
downloadable PDF/CSV too (only prescribing-information PDFs for already-
approved drugs exist under packageinserts.bms.com -- no pipeline PDF), so
this page is the sole source. See log.md.

The `subcategory` field on each listing is a slug (e.g.
"bms:tumor/1l-non-small-cell-lung-cancer") that must be resolved to its
human-readable label via the separate `therapeuticarea[].list[]` lookup
table also embedded in the same JSON blob.
"""

import json
import re
import urllib.request
from pathlib import Path

URL = "https://www.bms.com/research-and-development/pipeline.html"
HERE = Path(__file__).parent


def fetch_html() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def scrape_rows(html: str) -> list[dict]:
    import html as html_module

    m = re.search(r'<div id="pipeline-data"[^>]*>(.*?)</div>', html, re.S)
    if not m:
        raise ValueError("pipeline-data div not found -- BMS page structure may have changed")
    data = json.loads(html_module.unescape(m.group(1)))

    # subcategory slug -> human-readable indication label
    subcategory_labels = {
        item["name"]: item["value"]
        for area in data["therapeuticarea"]
        for item in area["list"]
    }
    # category slug -> human-readable therapeutic area label
    category_labels = {area["name"]: area["value"] for area in data["therapeuticarea"]}
    phase_labels = {p["value"]: p["name"] for p in data["phase"]}

    rows = []
    for listing in data["listings"]:
        rows.append(
            {
                "compound_name": strip_tags(listing["compoundname"]),
                "category": category_labels.get(listing["category"], listing["category"]),
                "indication": subcategory_labels.get(listing["subcategory"], listing["subcategory"]),
                "phase_label": phase_labels.get(listing["phaseTag"], listing["phaseTag"]),
                "research_area": strip_tags(listing.get("researcharea", "")),
                "nme_status": listing.get("nmedatastatus") or None,
                "registration_status": listing.get("registrationstatus") or None,
            }
        )
    return rows


def main():
    html = fetch_html()
    (HERE / "bms_pipeline_page.html").write_text(html)

    rows = scrape_rows(html)

    (HERE / "raw_pipeline.json").write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} raw rows to raw_pipeline.json")


if __name__ == "__main__":
    main()
