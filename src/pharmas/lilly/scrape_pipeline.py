"""Scrape Eli Lilly pipeline data via Playwright network interception.

Source: https://lilly.com/science/research-development/pipeline
The page loads data from an internal API (/v1/cdp-data) that requires auth.
Playwright can intercept the response when the JS widget fetches it.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main():
    from playwright.sync_api import sync_playwright

    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        def on_response(response):
            url = response.url
            if "/v1/cdp-data" in url and response.ok:
                try:
                    data = response.json()
                    captured.append(data)
                    print(f"Captured pipeline data from: {url}", file=sys.stderr)
                except Exception as e:
                    print(f"Failed to parse: {e}", file=sys.stderr)

        page.on("response", on_response)

        try:
            page.goto(
                "https://lilly.com/science/research-development/pipeline",
                wait_until="networkidle",
                timeout=60000,
            )
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"Navigation warning: {e}", file=sys.stderr)

        # Also grab the page body text as fallback
        body_text = page.locator("body").inner_text()
        (HERE / "page_text.txt").write_text(body_text)

        browser.close()

    if captured:
        raw_path = HERE / "raw_pipeline.json"
        raw_path.write_text(json.dumps(captured[0], indent=2))
        print(f"Saved pipeline data to {raw_path}", file=sys.stderr)

        molecules = captured[0].get("molecules", [])
        print(f"Molecules: {len(molecules)}", file=sys.stderr)
        if molecules:
            print(f"Sample keys: {list(molecules[0].keys())}", file=sys.stderr)
            print(f"Sample: title={molecules[0].get('title')}, phase={molecules[0].get('phase')}, indication={molecules[0].get('indication')}, ta_id={molecules[0].get('therapeutic_area_id')}", file=sys.stderr)
    else:
        print("No pipeline data captured - saved page text as fallback", file=sys.stderr)


if __name__ == "__main__":
    main()
