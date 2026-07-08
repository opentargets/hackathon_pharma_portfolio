"""Scrape Sanofi's pipeline page into raw, unmapped rows.

Pass 1 of the two-pass workflow (scrape raw -> map to schema separately).
No schema mapping happens here.

Site: https://sanofi.com/en/our-science/our-pipeline

Confirmed via `curl` first (per instructions.md) that the raw HTML is a fully
client-rendered React/MUI SPA with no embedded JSON blob -- genuinely needs a
browser, unlike MSD which turned out to be static despite looking dynamic.

Once rendered, each clinical-stage project is one row with Name / Phase
(1-2-3-R badges, current phase highlighted with a purple-filled badge,
`.css-yaszgn-*` vs the unfilled `.css-3ha4an-*`) / Description (free-text
MoA) / Therapeutic Area / Indication already static in the DOM -- no click
needed for those. Every row is rendered TWICE (a labelled desktop copy and an
unlabelled responsive-duplicate copy sharing the same
`aria-label="Expand details for <name> in <indication>"` button) -- exactly
like MSD's mobile/desktop duplication. Filtering to `is_visible()` buttons
narrows 154 buttons down to 77 (matches docs/sources.md's "77 clinical-stage
projects").

Clicking a row's "Expand details" button (user confirmed this is worth
doing) reveals three more fields not present in the static DOM: Collaboration
(e.g. "Developed in collaboration with Regeneron"), Notes, and Expected
Submission Timeline. These are extracted by walking to each field's own
container div, which holds exactly 3 <p> tags (mobile label, desktop label,
value) -- the value is always the last one, so this doesn't depend on
Emotion's generated class-name hashes.
"""

import csv
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

URL = "https://sanofi.com/en/our-science/our-pipeline"
HERE = Path(__file__).parent
OUT_JSON = HERE / "raw_pipeline.json"
OUT_CSV = HERE / "raw_pipeline.csv"

ROW_CONTAINER_JS = """
el => {
    // Climb as high as possible while the ancestor still describes exactly
    // one row (single "Description" occurrence) -- the expanded
    // Collaboration/Notes/Timeline accordion only mounts into the DOM on
    // click, as a *sibling* of the row's own summary block a couple of
    // levels up, not nested inside it, so stopping at the first ancestor
    // that merely contains "Name"/"Description"/"Therapeutic Area" misses
    // it entirely. Stop climbing once a second "Description" would appear,
    // which means we have overshot into the multi-row list container.
    let node = el;
    let match = null;
    for (let i = 0; i < 12; i++) {
        node = node.parentElement;
        if (!node) break;
        const txt = node.textContent;
        const descCount = (txt.match(/Description/g) || []).length;
        if (txt.includes("Name") && txt.includes("Therapeutic Area") && descCount === 1) {
            match = node;
        } else if (descCount > 1) {
            break;
        }
    }
    return match;
}
"""


def field_value(soup, label):
    """Find a <p>label</p> and return the sibling <p> holding its value.

    Static base fields (Name, Therapeutic Area, Indication) render as exactly
    two <p> siblings: [label, value]. Expanded fields (Collaboration, Notes,
    Expected Submission Timeline) render as three: [mobile label, desktop
    label, value]. Either way the value is the last <p> child.
    """
    label_tag = soup.find("p", string=label)
    if label_tag is None:
        return None
    siblings = label_tag.parent.find_all("p", recursive=False)
    if not siblings:
        return None
    return siblings[-1].get_text(strip=True)


def parse_row(html, expanded_html):
    soup = BeautifulSoup(html, "html.parser")

    name = field_value(soup, "Name")
    therapeutic_area = field_value(soup, "Therapeutic Area")
    indication = field_value(soup, "Indication")

    desc_label = soup.find("p", string="Description")
    description = None
    if desc_label is not None:
        desc_value_div = desc_label.parent.find_all("div", recursive=False)
        if desc_value_div:
            # last div in the Description box is `.css-knyz9o` (MoA text);
            # the sibling before it is the info-icon tooltip button.
            description = desc_value_div[-1].get_text(strip=True)

    phase_label = soup.find("p", string="Phase")
    active_phases = []
    if phase_label is not None:
        grid = phase_label.parent.find_all("div", recursive=False)
        if grid:
            badge_grid = grid[-1]
            for badge in badge_grid.find_all("div", recursive=False):
                if "css-yaszgn-MuiTypography-root" in badge.get("class", []):
                    active_phases.append(badge.get_text(strip=True))

    expanded_soup = BeautifulSoup(expanded_html, "html.parser")
    collaboration = field_value(expanded_soup, "Collaboration")
    notes = field_value(expanded_soup, "Notes")
    timeline = field_value(expanded_soup, "Expected Submission Timeline")

    return {
        "name": name,
        "phase_badges": active_phases,
        "description": description,
        "therapeutic_area": therapeutic_area,
        "indication": indication,
        "collaboration": collaboration,
        "notes": notes,
        "expected_submission_timeline": timeline,
    }


def main():
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(URL, wait_until="networkidle", timeout=60000)

        try:
            page.locator('button:has-text("Accept")').first.click(timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        buttons = page.locator('[aria-label^="Expand details for"]')
        handles = [
            h for h in buttons.element_handles() if h.is_visible()
        ]
        print(f"Found {len(handles)} visible project rows (of {buttons.count()} total incl. responsive duplicates)")

        for i, btn in enumerate(handles):
            aria_label = btn.get_attribute("aria-label") or ""
            m = re.match(r"^Expand details for (.+) in (.+)$", aria_label)
            label_name, label_indication = (m.group(1), m.group(2)) if m else (None, None)

            container = btn.evaluate_handle(ROW_CONTAINER_JS)
            container_el = container.as_element()
            if container_el is None:
                print(f"  [{i}] {aria_label!r}: could not locate row container, skipping")
                continue

            before_html = container_el.evaluate("el => el.outerHTML")

            btn.evaluate("el => el.click()")
            page.wait_for_timeout(400)

            after_html = container_el.evaluate("el => el.outerHTML")

            row = parse_row(before_html, after_html)
            row["aria_label_name"] = label_name
            row["aria_label_indication"] = label_indication
            rows.append(row)
            print(f"[{i+1}/{len(handles)}] {row['name']} | {row['phase_badges']} | {row['indication']}")

        browser.close()

    with open(OUT_JSON, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    fieldnames = [
        "name",
        "phase_badges",
        "description",
        "therapeutic_area",
        "indication",
        "collaboration",
        "notes",
        "expected_submission_timeline",
        "aria_label_name",
        "aria_label_indication",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            r = dict(r)
            r["phase_badges"] = ";".join(r["phase_badges"])
            writer.writerow(r)

    print(f"\nSaved {len(rows)} rows to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
