"""Explore BI pipeline page with DynamicFetcher (Playwright via scrapling)."""
import json
from scrapling.fetchers import DynamicFetcher

URL = "https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline"
OUT = "src/pharmas/boehringer_ingelheim/exploration_dump.json"

page = DynamicFetcher.fetch(
    URL,
    headless=True,
    network_idle=True,
    timeout=120000,
)

print(f"Status: {page.status}")
print(f"Final URL: {page.url}")

full_text = page.get_all_text(strip=True)
print(f"Text length: {len(full_text)}")
print(f"\n=== TEXT ===\n{full_text[:5000]}")

info = {
    "status": page.status,
    "url": page.url,
    "text_length": len(full_text),
    "full_text": full_text,
}

with open(OUT, "w") as f:
    json.dump(info, f, indent=2, ensure_ascii=False)

print(f"\nSaved to {OUT}")
