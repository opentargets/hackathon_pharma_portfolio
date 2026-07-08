"""Scrape MSD's pipeline page into raw, unmapped rows.

Pass 1 of the two-pass workflow (scrape raw -> map to schema separately).
No schema mapping happens here.

The pipeline page (https://www.msd.com/research/product-pipeline/) turned out
to be fully static: `curl`ing it returns the complete data already rendered
into `<tr class="pipeline-program">` rows with `data-*` attributes and nested
`.pipeline-program-indication` blocks (name, code, therapeutic area, modality,
free-text mechanism-of-action paragraph, and one row per indication with a
phase slug + NCT trial references). No browser/Playwright needed.

Each `tr.pipeline-program` row renders its indications TWICE in the DOM (once
in a `.pipeline-program-indications` div for mobile, once in a `<table>` for
desktop) — this script reads only the `.pipeline-program-indications` copy to
avoid doubling every row.

The official pipeline PDF (`msd_pipeline_2Q2026.pdf`, downloaded alongside
this script for provenance) additionally has an "Approvals" page (4 items
approved in the last 3 months) that the live webpage doesn't expose as a
phase at all — those 4 are hand-transcribed into `pdf_approvals` below since
there are only 4 and they don't follow the repeating DOM structure above.
See log.md for the cross-check against the webpage and the reconciliation
decision (each becomes an extra row tagged phase "Registered", alongside the
webpage's own row for that same drug/indication in whatever phase it shows
for other regions).
"""

import json
import re
import urllib.request
from pathlib import Path

URL = "https://www.msd.com/research/product-pipeline/"
HERE = Path(__file__).parent

# Hand-transcribed from msd_pipeline_2Q2026.pdf, page 7 ("Approvals1" /
# "obtained within the last 3 months"). Not present anywhere in the live
# webpage's phase filter (Under Review / Phase 3 / Phase 2 only).
PDF_APPROVALS = [
    {
        "source": "pdf_approvals",
        # data_name matches the webpage's own program name for MK-1654
        # ("ENFLONSIA(TM)") so this compound gets one consistent asset_name
        # across both its webpage row and this PDF-only row.
        "data_name": "ENFLONSIA",
        "data_code": "(MK-1654)",
        "brand": "clesrovimab",
        "therapeutic_area": "respiratory",
        "indication_title": "Respiratory Syncytial Virus",
        "region": "EU",
        "trial_text": "NCT04767373, NCT04938830",
        "moa_text": None,
        "notes": "Approval obtained within the last 3 months (MSD pipeline PDF, 2Q2026, page 7).",
    },
    {
        "source": "pdf_approvals",
        # Matches the webpage's own spacing for MK-8591A exactly (its PDF
        # rendering uses "doravirine (+) islatravir" instead) so this
        # compound gets one consistent asset_name across both rows.
        "data_name": "doravirine + islatravir",
        "data_code": "(MK-8591A)",
        "brand": "IDVYNSO",
        "therapeutic_area": "antiviral",
        "indication_title": "HIV-1 Infection",
        "region": "US, JPN",
        "trial_text": (
            "MK-8591A-033; NCT04776252, ILLUMINATE SWITCH A; NCT04223778, "
            "ILLUMINATE NAIVE; NCT04233879, ILLUMINATE SWITCH B; NCT04223791, "
            "ILLUMINATE HTE; NCT04233216, MK-8591A-051; NCT05631093, "
            "MK-8591A-052; NCT05630755, MK-8591A-053; NCT05705349, "
            "MK-8591A-054; NCT05766501"
        ),
        "moa_text": None,
        "notes": "Approval obtained within the last 3 months (MSD pipeline PDF, 2Q2026, page 7).",
    },
    {
        "source": "pdf_approvals",
        "data_name": "KEYTRUDA",
        "data_code": "(MK-3475)",
        "brand": "KEYTRUDA",
        "therapeutic_area": "oncology",
        "indication_title": "Platinum-Resistant Recurrent Ovarian Cancer",
        "region": "EU",
        "trial_text": "KNB96; NCT05116189",
        "moa_text": None,
        "notes": "Approval obtained within the last 3 months (MSD pipeline PDF, 2Q2026, page 7).",
    },
    {
        "source": "pdf_approvals",
        "data_name": "KEYTRUDA QLEX",
        "data_code": "(MK-3475A)",
        "brand": "KEYTRUDA QLEX",
        "therapeutic_area": "oncology",
        "indication_title": "Platinum-Resistant Recurrent Ovarian Cancer",
        "region": "EU",
        "trial_text": "KNB96",
        "moa_text": None,
        "notes": (
            "Approval obtained within the last 3 months (MSD pipeline PDF, 2Q2026, page 7). "
            "MK-3475A to be marketed under the trade name KEYTRUDA SC in the EU."
        ),
    },
]


def fetch_html() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def scrape_webpage_rows(html: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for prog in soup.select("tr.pipeline-program"):
        # Prefer the visible heading over the `data-name` attribute: MK-3475A's
        # attribute is "KEYTRUDAA" (a bug in MSD's own markup) while the
        # heading correctly reads "KEYTRUDA QLEX (TM)", matching the PDF.
        name_el = prog.select_one(".pipeline-program-header .pipeline-program-name")
        if name_el is not None:
            name_el = BeautifulSoup(str(name_el), "html.parser")
            code_nested = name_el.select_one(".pipeline-program-code")
            if code_nested is not None:
                code_nested.extract()
            data_name = " ".join(name_el.get_text(strip=True).split())
        else:
            data_name = prog.get("data-name", "").strip()
        data_code = prog.get("data-code", "").strip()
        therapeutic_area = prog.get("data-therapeutic-area", "").strip()
        modality = prog.get("data-modality", "").strip()

        content_div = prog.select_one(".pipeline-program-content")
        moa_text = content_div.get_text(" ", strip=True) if content_div else None

        indications_div = prog.select_one(".pipeline-program-indications")
        indication_blocks = (
            indications_div.select(".pipeline-program-indication")
            if indications_div
            else []
        )
        for ind in indication_blocks:
            title_el = ind.select_one(".pipeline-program-indication-title")
            content_el = ind.select_one(".pipeline-program-indication-content")
            # Some indications (12/105) carry their regulatory-status region
            # (e.g. "Under Review (JPN)") in a separate phase-bars text node
            # instead of the indication title itself -- easy to miss since
            # most indications render as plain progress-bar dots with no text.
            phase_text_el = ind.select_one(".pipeline-phase-bars .pipeline-phase-text")
            rows.append(
                {
                    "source": "webpage",
                    "data_name": data_name,
                    "data_code": data_code,
                    "therapeutic_area": therapeutic_area,
                    "modality": modality,
                    "moa_text": moa_text,
                    "indication_title": title_el.get_text(strip=True)
                    if title_el
                    else None,
                    "phase_slug": ind.get("data-phase-slug"),
                    "phase_text": phase_text_el.get_text(strip=True)
                    if phase_text_el
                    else None,
                    "trial_text": re.sub(
                        r"^\(|\)$", "", content_el.get_text(strip=True)
                    )
                    if content_el
                    else None,
                }
            )
    return rows


def main():
    html = fetch_html()
    (HERE / "msd_pipeline_page.html").write_text(html)

    rows = scrape_webpage_rows(html)
    rows.extend(PDF_APPROVALS)

    (HERE / "raw_pipeline.json").write_text(json.dumps(rows, indent=2))
    print(f"Wrote {len(rows)} raw rows ({len(rows) - len(PDF_APPROVALS)} from "
          f"webpage + {len(PDF_APPROVALS)} from PDF approvals page) to raw_pipeline.json")


if __name__ == "__main__":
    main()
