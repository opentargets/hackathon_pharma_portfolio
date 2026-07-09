"""Scrape J&J pipeline data from the JS widget via Playwright.

The site is behind Cloudflare. Playwright renders the full pipeline
with phase info. Extract all entries from the rendered DOM.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        page.goto(
            "https://investor.jnj.com/pipeline/development-pipeline/",
            wait_until="networkidle",
            timeout=60000,
        )
        page.wait_for_timeout(5000)

        # Extract all pipeline cards
        entries = page.evaluate("""() => {
            const items = [];
            const cards = document.querySelectorAll('[class*="pipeline"] [class*="card"], .pipeline-card, [class*="indication"], .indication-item');
            // Fallback: try to find structured entries
            const allEls = document.querySelectorAll('body *');
            const textBlocks = [];
            let currentTA = '';
            let currentPhase = '';

            // Find sections by looking for therapeutic area headers
            const taHeaders = document.querySelectorAll('h2, h3, h4, strong');
            const pipelineData = [];
            let ta = '';

            for (const el of allEls) {
                const text = el.textContent.trim();
                if (!text) continue;

                // Check if this is a TA header
                const tagName = el.tagName.toLowerCase();
                if (tagName === 'h2' || tagName === 'h3' || (tagName === 'strong' && el.children.length === 0)) {
                    const possibleTA = text;
                    if (['Oncology', 'Immunology', 'Neuroscience', 'Select Other Areas', 'Pulmonary Hypertension',
                         'Infectious Diseases', 'Cardiovascular'].some(t => possibleTA.includes(t))) {
                        ta = possibleTA;
                        continue;
                    }
                }
            }

            // Get all text blocks in order
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const blocks = [];
            while (walker.nextNode()) {
                const t = walker.currentNode.textContent.trim();
                if (t) blocks.push(t);
            }

            // Parse: look for pattern: drug name -> indication -> phase
            const phases = ['Phase 1', 'Phase 2', 'Phase 3', 'Registration'];
            let currentTA2 = '';

            for (let i = 0; i < blocks.length; i++) {
                const b = blocks[i];
                // TA headers
                if (/^(Oncology|Immunology|Neuroscience|Select Other Areas|Pulmonary Hypertension)/.test(b)) {
                    currentTA2 = b;
                    continue;
                }
                // Skip navigation/menu items
                if (b.length < 3 || /^(Skip|Search|Download|Pipeline|Financials|Therapeutic|Changes|Phase|All$|jnj\.com)/.test(b)) continue;
                if (b === 'All' || b === 'Phase' || b === 'Changes') continue;
                if (/^\d+ of \d+/.test(b)) continue;

                // Look for asset name followed by indication followed by phase
                if (i + 2 < blocks.length) {
                    const next1 = blocks[i + 1];
                    const next2 = blocks[i + 2];
                    if (phases.includes(next2) && b !== next1) {
                        // b = asset name, next1 = indication, next2 = phase
                        const assetMatch = b.match(/^([^(]+)\s*\(([^)]+)\)/);
                        pipelineData.push({
                            asset_name: b,
                            indication: next1,
                            phase: next2,
                            therapeutic_area: currentTA2
                        });
                        i += 2;
                        continue;
                    }
                }
            }

            return JSON.stringify(pipelineData);
        }""")

        # Save full page content as HTML for backup
        content = page.content()
        (HERE / "page_content.html").write_text(content)

        # Also get all text
        body_text = page.locator("body").inner_text()
        (HERE / "page_text.txt").write_text(body_text)

        print(f"Page saved ({len(content)} chars HTML, {len(body_text)} chars text)")

        result = json.loads(entries)
        print(f"Extracted {len(result)} pipeline entries")

        raw_path = HERE / "raw_pipeline.json"
        raw_path.write_text(json.dumps(result, indent=2))
        print(f"Saved to {raw_path}")

        # Print sample
        for r in result[:5]:
            print(f"  {r['asset_name'][:40]:40s} | {r['indication'][:40]:40s} | {r['phase']:15s} | {r.get('therapeutic_area','')}")

        browser.close()


if __name__ == "__main__":
    main()
