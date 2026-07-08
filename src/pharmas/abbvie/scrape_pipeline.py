"""Scrape AbbVie's pipeline page into raw, unmapped rows.

Pass 1 of the two-pass workflow (scrape raw -> map to schema separately).
No schema mapping happens here.

Site: https://www.abbvie.com/science/pipeline.html

docs/sources.md filed AbbVie as Tier 4 ("narrative text, no structured
table") -- that's stale. Plain `curl` gets Cloudflare-blocked (403), but a
real browser fetch shows the page is *not* narrative prose at all: every
asset is a `div.cmp-pipeline` with the full record embedded as static
`data-*` attributes (data-title, data-asset-focus-area, data-asset-type,
data-asset-target, data-asset-description, data-asset-indication,
data-asset-phases) plus a nested per-indication table
(`.phases-section .phase-element .phases-container`) giving indication /
region / phase-status per row. No click-to-reveal interaction is needed --
Cloudflare is the only thing standing between `curl` and the full dataset,
so a single stealthy-fetch (browser-based, to pass the Cloudflare check) is
enough; this is unlike Novo Nordisk/Sanofi where data only appears after
clicking each item.

Each row in the nested table is rendered twice (a `desktop-element` copy and
a `mobile-element` copy) -- same duplication pattern seen on MSD and Sanofi.
Only `desktop-element` copies are read here to avoid double-counting.

57 top-level asset cards (51 data-type="pharmaceutical" + 6
data-type="devices", the Aesthetics/facial-filler line), 97 asset x
indication rows -- matches the page's own "~90 compounds, devices or
indications in development" stat closely enough (that figure appears to be
rounded/approximate on AbbVie's side).
"""

import csv
import json
import re
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

URL = "https://www.abbvie.com/science/pipeline.html"
HERE = Path(__file__).parent
OUT_JSON = HERE / "raw_pipeline.json"
OUT_CSV = HERE / "raw_pipeline.csv"


def first(el, selector):
    matches = el.css(selector)
    return matches[0] if matches else None


def clean(s):
    if s is None:
        return None
    s = s.replace("∕", "/")  # AbbVie uses U+2215 DIVISION SLASH instead of "/"
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_asset(card):
    attrs = card.attrib
    asset_type = "device" if attrs.get("data-type") == "devices" else "pharmaceutical"

    rows = []
    for phases_container in card.css(".phases-section .phase-element .phases-container"):
        indication_el = first(phases_container, "div.col1 span.phase-title")
        indication = clean(indication_el.text) if indication_el is not None else None

        region_el = first(phases_container, "div.col2.desktop-element span.region-label")
        region = clean(region_el.text) if region_el is not None else None

        status_el = first(phases_container, "div.col3.desktop-element span.phase-status")
        phase_status_class = None
        phase_status_label = None
        if status_el is not None:
            classes = [c for c in status_el.attrib.get("class", "").split() if c != "phase-status" and c != "desktop-element"]
            phase_status_class = classes[0] if classes else None
            phase_status_label = clean(status_el.text)

        if indication is None and phase_status_class is None:
            continue  # empty placeholder row, no real data

        rows.append(
            {
                "indication": indication,
                "region": region,
                "phase_status_class": phase_status_class,
                "phase_status_label": phase_status_label,
            }
        )

    return {
        "asset_id": attrs.get("id"),
        "asset_type": asset_type,
        "data_title": clean(attrs.get("data-title")),
        "data_asset_focus_area": clean(attrs.get("data-asset-focus-area")),
        "data_asset_type": clean(attrs.get("data-asset-type")),
        "data_asset_target": clean(attrs.get("data-asset-target")),
        "data_asset_tags": clean(attrs.get("data-asset-tags")),
        "data_asset_indication": clean(attrs.get("data-asset-indication")),
        "data_asset_description": clean(attrs.get("data-asset-description")),
        "data_asset_phases": clean(attrs.get("data-asset-phases")),
        "indication_rows": rows,
    }


def main():
    page = StealthyFetcher.fetch(URL, solve_cloudflare=True)
    print(f"Fetched {URL} -> HTTP {page.status}")

    cards = page.css("div.cmp-pipeline")
    # the container div itself also matches "div.cmp-pipeline" via substring
    # class match on some selector engines -- guard by requiring data-title
    cards = [c for c in cards if c.attrib.get("data-title")]
    print(f"Found {len(cards)} asset cards")

    assets = [parse_asset(c) for c in cards]
    total_indication_rows = sum(len(a["indication_rows"]) for a in assets)
    print(f"Found {total_indication_rows} asset x indication rows")

    with open(OUT_JSON, "w") as f:
        json.dump(assets, f, indent=2, ensure_ascii=False)

    flat_rows = []
    for a in assets:
        base = {k: v for k, v in a.items() if k != "indication_rows"}
        if not a["indication_rows"]:
            flat_rows.append({**base, "indication": None, "region": None, "phase_status_class": None, "phase_status_label": None})
        for r in a["indication_rows"]:
            flat_rows.append({**base, **r})

    fieldnames = list(flat_rows[0].keys()) if flat_rows else []
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)

    print(f"Saved {len(assets)} assets ({len(flat_rows)} flat rows) to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
