"""Scrape CSL's pipeline page into raw, unmapped rows.

Pass 1 of the two-pass workflow (scrape raw -> map to schema separately).
No schema mapping happens here.

The pipeline page (https://www.csl.com/research-and-development/product-pipeline)
turned out to be fully static: `curl`ing it returns the complete data already
rendered into `<a class="p-item">` blocks nested under `.category-phase`
containers (one per Phase I/II/III/Registration bucket), each with a visible
name (`.p-name`), a free-text blurb blending mechanism-of-action + indication
(`.p-content`, shown as a "popup" on click but already present in the raw
HTML -- no browser/interaction needed), and a `data-filter` UUID that maps to
one of 5 therapeutic-area checkboxes rendered earlier on the same page. No
PDF/CSV pipeline document exists for CSL (checked csl.com and investors.csl.com
for one) -- the webpage is the only source.
"""

import json
import re
import urllib.request
from pathlib import Path

URL = "https://www.csl.com/research-and-development/product-pipeline"
HERE = Path(__file__).parent

# UUIDs from the `.ui-checkbox-item[data-filter]` therapeutic-area filter
# checkboxes, mapped to their visible label text.
FILTER_MAP = {
    "c597cf79-503f-4a9b-aedf-dd827df83f72": "Immunoglobulins",
    "1fc84135-2abc-4e56-81ac-8b73553925f3": "Hematology",
    "6812871b-905b-45f8-858b-569e4bc72d01": "Cardiovascular & Renal",
    "2fd087fb-b1fb-433d-b25b-6a41dd4e20ea": "Transplant & Immunology",
    "7aa5d6a4-58b6-485d-bdec-4558e10c9d27": "Vaccines",
}

PHASE_LABELS = {
    "1": "Phase I",
    "2": "Phase II",
    "3": "Phase III",
    "4": "Registration / Post Registration",
}


def clean_text(el) -> str | None:
    """Extract element text, preserving whitespace at inline-tag boundaries.

    `get_text(strip=True)` strips each text node individually then joins
    with no separator, silently dropping a real space when it falls right
    at a `<sup>...</sup>` tag boundary (e.g. CSL's own markup:
    `HIZENTRA<sup>&reg;</sup> (SCIg)...` -> stripped to
    `HIZENTRA®(SCIg)...`, losing the space -- caught by a user cross-check
    against a manual copy of the live page, 22/34 names affected).
    """
    if el is None:
        return None
    text = re.sub(r"\s+", " ", el.get_text()).strip()
    return text or None


def fetch_html() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def scrape_footnotes(html: str) -> list[str]:
    """The page has a `section.footnotes` below the pipeline table:
    a `*`-marker explainer ("Co-development project...") and an "as at"
    freshness date -- neither is exposed anywhere in the pipeline items
    themselves, easy to miss if only the `.product-pipeline` section is read.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    footnotes_section = soup.select_one("section.footnotes")
    if footnotes_section is None:
        return []
    return [p.get_text(strip=True) for p in footnotes_section.select("p")]


def scrape_webpage_rows(html: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one("section.product-pipeline")
    rows = []
    for category in section.select(".product-pipeline__category"):
        headline_el = category.select_one(".category-headline")
        headline = headline_el.get_text(strip=True) if headline_el else None
        for phase_div in category.select(".category-phase"):
            phase_num = phase_div.get("data-phase")
            phase_label = PHASE_LABELS.get(phase_num, phase_num)
            for item in phase_div.select("a.p-item"):
                name_el = item.select_one(".p-name")
                content_el = item.select_one(".p-content")
                filt = item.get("data-filter")
                rows.append(
                    {
                        "category": headline,
                        "phase_num": phase_num,
                        "phase_label": phase_label,
                        "name": clean_text(name_el),
                        "content": clean_text(content_el),
                        "therapeutic_area": FILTER_MAP.get(filt, filt),
                    }
                )
    return rows


def main():
    html = fetch_html()
    (HERE / "csl_pipeline_page.html").write_text(html)

    rows = scrape_webpage_rows(html)
    footnotes = scrape_footnotes(html)

    output = {"rows": rows, "footnotes": footnotes}
    (HERE / "raw_pipeline.json").write_text(json.dumps(output, indent=2))
    print(f"Wrote {len(rows)} raw rows + {len(footnotes)} footnotes to raw_pipeline.json")


if __name__ == "__main__":
    main()
