---
title: Sources
nav_order: 2
---


## Sources by Tier

### Tier 1 — Clean PDF, Stable URL, Machine-Readable Table

PDFs with a clear tabular layout, and full pipeline coverage (including early phase).

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Pfizer | `https://www.pfizer.com/science/drug-product-pipeline` | Quarterly PDF. Columns: Compound / MoA / Indication / Phase / Submission Type See [`log.md`](src/pharmas/pfizer/log_20260709_144746.md) | Done — see [`src/pharmas/pfizer/log.md`](src/pharmas/pfizer/log_20260709_145421.md) |
| AstraZeneca | `https://www.astrazeneca.com/our-therapy-areas/pipeline.html` | Server-rendered HTML (no JS needed). Fields: Name, Mechanism, Area under investigation, Phase, Molecule size. PDF also exists but is older (Feb vs Apr 2026) and less rich. See [`src/pharmas/astrazeneca/log.md`](../src/pharmas/astrazeneca/log.md) | ✅ |
| Novartis | `https://www.novartis.com/research-development/novartis-pipeline` | Server-rendered HTML (Drupal View, 6 pages, no JS needed). See [`src/pharmas/novartis/log.md`](../src/pharmas/novartis/log.md) | ✅ |
| Roche | `roche.com/solutions/pipeline` | Semi-annual (H1/H2) | ✅ |
| Boehringer Ingelheim | `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline` | Stable URL | TODO |
| Takeda | `takeda.com/science/pipeline/` → "DOWNLOAD THE PDF" | Full pipeline PDF. Position-aware word extraction used — table extraction was unreliable due to merged cells. See [`src/pharmas/takeda/log.md`](../src/pharmas/takeda/log.md) | ✅ |

### Tier 2 — PDF Available but with Parsing Caveats

PDFs exist but may be chart-style layouts, exclude Phase 1, or cover only late-stage assets.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Amgen | `https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf` | Quarterly PDF described as a "chart" — likely vector-based, not a literal table. | TODO |
| Merck & Co. | `https://www.msd.com/research/product-pipeline/` | PDF also available but is a "chart" (positional grid, not a table); the live pipeline page is static HTML with richer per-indication data (MoA, NCT IDs) and was used as primary source instead. Phase 1 candidates not shown. | ✅ |
| BMS | `https://www.bms.com/research-and-development/pipeline.html` | Live HTML pipeline page. Compound + indication pairs per area, not a strict table. Excludes collaborations. | TODO |
| Bayer | `https://www.bayer.com/en/pharma/development-pipeline` | ~30 late-stage projects only (not full pipeline). | TODO |
| GSK | `gsk.com/en-gb/innovation/pipeline` |  CSV is provided in this case | ✅ |

### Tier 3 — Interactive JS Widget (Network-Tab / Playwright)

The pipeline is rendered dynamically. Data must be extracted from the network tab (XHR/Fetch JSON) or via headless browser.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| J&J | `https://investor.jnj.com/pipeline/development-pipeline/` | Fully JS-rendered widget with drug-name search. Check network tab for underlying API call. PDF available as well | TODO |
| Eli Lilly | `https://lilly.com/science/research-development/pipeline` | Interactive — click each molecule box to expand. Check network tab for JSON. | TODO |
| Sanofi | `https://sanofi.com/en/our-science/our-pipeline` | Interactive filterable tracker. 77 clinical-stage projects (2026). | ✅ |
| Novo Nordisk | `https://novonordisk.com/science-and-technology/r-d-pipeline.html` | Interactive, filterable by phase and therapeutic area. Small pipeline, diabetes/obesity-heavy. | ✅ |
| Gilead | `https://gilead.com/science-and-medicine/pipeline` | ~58 clinical-stage programs. DOM may be parseable without full Playwright. | TODO |
| Teva | `https://tevapharm.com/science/pipeline/` | Interactive filterable tracker. Mix of innovative + biosimilars. | TODO |
| CSL | `https://www.csl.com/research-and-development/product-pipeline` | You have to interact to extract the indication. | TODO |
| Merck KGaA | `https://www.merckgroup.com/en/research/healthcare-pipeline.html` | Interactive filterable tracker. | TODO |
| AbbVie | `https://www.abbvie.com/science/pipeline.html` | Cloudflare-gated (plain `curl` gets 403), but once fetched via browser the data is fully static HTML — 57 assets / 97 asset-indication rows embedded as `data-*` attributes, no click-to-reveal needed. No PDF/CSV exists. Devices (6 aesthetics assets) use a distinct phase scale (Concept/Feasibility/Development/Confirmation/Approved/Launched) mapped onto the shared Phase enum. | Done — see [`src/pharmas/abbvie/log.md`](../src/pharmas/abbvie/log.md) |


## Strategy (High-Level)

Detailed strategy discussions are tracked as **GitHub Issues** in this repository. High-level approach:

1. **Start with Tier 1** — build the pipeline ingestion pipeline on the cleanest sources first (Pfizer, AZ, Novartis, Roche, BI, Takeda). Validate parsing with pdfplumber / Camelot.
2. **Tier 2** — adapt parsers for chart-style PDFs (Amgen, Merck & Co.) and semi-structured documents (BMS, Bayer). May require OCR fallback (pytesseract).
3. **Tier 3** — inspect network-layer calls for each JS widget to find JSON endpoints; fall back to Playwright for dynamic rendering.

All extracted data should map to the unified schema defined in [`data-model.md`](data-model.md).
