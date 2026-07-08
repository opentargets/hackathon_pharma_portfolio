"""Scrape Novo Nordisk R&D pipeline page (JS widget, no static table).

Site: https://www.novonordisk.com/science-and-technology/r-d-pipeline.html
Each drug is a clickable div (`.area-item`) inside a `.rndarea-wrapper <area> <phase>`
cell. Clicking fires an AJAX call to /bin/nncorp/rnd-pipeline and fills a dialog
(`.rnddialog-wrapper`) with a description paragraph. This script clicks through every
drug button and dumps raw row-level data (name, area, phase, description) to JSON/CSV.
No schema mapping yet, per instructions.md.
"""

import csv
import json
import time

from playwright.sync_api import sync_playwright

URL = "https://www.novonordisk.com/science-and-technology/r-d-pipeline.html"
OUT_JSON = "pharmas/novonordisk/raw_pipeline.json"
OUT_CSV = "pharmas/novonordisk/raw_pipeline.csv"


def main():
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)

        try:
            page.locator('button:has-text("Accept")').first.click(timeout=3000)
        except Exception:
            pass
        page.wait_for_timeout(500)

        count = page.locator(".area-item").count()
        print(f"Found {count} drug buttons")

        for i in range(count):
            btn = page.locator(".area-item").nth(i)
            name = (btn.get_attribute("aria-label") or "").replace(" Open Dialog", "").strip()
            wrapper_class = btn.evaluate("el => el.closest('.rndarea-wrapper').className")
            parts = wrapper_class.replace("rndarea-wrapper", "").split()
            area = parts[0] if len(parts) > 0 else ""
            phase = parts[1] if len(parts) > 1 else ""

            btn.scroll_into_view_if_needed()
            btn.click(timeout=10000)
            page.wait_for_timeout(1500)

            desc_html = ""
            desc_text = ""
            try:
                desc_el = page.locator(
                    ".rnddialog-wrapper .dialog-content .paragraph-l"
                ).first
                desc_html = desc_el.inner_html(timeout=5000)
                desc_text = desc_el.inner_text(timeout=5000)
            except Exception as e:
                print(f"  [{i}] {name}: no description found ({e})")

            rows.append(
                {
                    "name": name,
                    "area": area,
                    "phase": phase,
                    "description_text": desc_text.strip(),
                    "description_html": desc_html.strip(),
                }
            )
            print(f"[{i+1}/{count}] {name} | {area} | {phase} | {desc_text[:60]!r}")

            # close dialog
            try:
                page.locator(".rnddialog-wrapper .icon-times-white").first.click(timeout=3000)
            except Exception:
                page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        browser.close()

    with open(OUT_JSON, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "area", "phase", "description_text"])
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "name": r["name"],
                    "area": r["area"],
                    "phase": r["phase"],
                    "description_text": r["description_text"],
                }
            )

    print(f"\nSaved {len(rows)} rows to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
