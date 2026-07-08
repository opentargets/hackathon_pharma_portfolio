---
title: Sources
nav_order: 2
---


## Sources by Tier

### Tier 1 — Clean PDF, Stable URL, Machine-Readable Table

PDFs with a clear tabular layout, and full pipeline coverage (including early phase).

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Pfizer | `https://www.pfizer.com/science/drug-product-pipeline` | Quarterly PDF. Columns: Compound / MoA / Indication / Phase / Submission Type | TODO |
| AstraZeneca | `https://www.astrazeneca.com/our-therapy-areas/pipeline.html` | Annual PDF. Columns: Compound / Mechanism / Area Under Investigation | TODO |
| Novartis | `novartis.com/research-development/novartis-pipeline` → PDF | Quarterly PDF linked from pipeline page | TODO |
| Roche | `roche.com/solutions/pipeline` | Semi-annual (H1/H2) | Done — see [`src/pharmas/roche/log.md`](../src/pharmas/roche/log.md) |
| Boehringer Ingelheim | `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline` | Stable URL | TODO |
| Takeda | `takeda.com/science/pipeline/` → "DOWNLOAD THE PDF" | Full pipeline PDF + oncology-specific PDF at `takedaoncology.com/science/pipeline/` | TODO |

### Tier 2 — PDF Available but with Parsing Caveats

PDFs exist but may be chart-style layouts, exclude Phase 1, or cover only late-stage assets.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Amgen | `https://www.amgenpipeline.com/-/media/Themes/Amgen/amgenpipeline-com/amgenpipeline-com/PDF/amgen-pipeline-chart.pdf` | Quarterly PDF described as a "chart" — likely vector-based, not a literal table. | TODO |
| Merck & Co. | `https://www.msd.com/research/product-pipeline/` | PDF also available. "chart." Phase 1 candidates not shown. | TODO |
| BMS | `https://annual-report.bms.com/assets/bms-ar/documents/2025/2025-bms-development-portfolio.pdf` | Annual PDF only. Compound + indication pairs per area, not a strict table. Excludes collaborations. | TODO |
| Bayer | `https://www.bayer.com/en/pharma/development-pipeline` | ~30 late-stage projects only (not full pipeline). | TODO |
| GSK | `gsk.com/en-gb/innovation/pipeline` |  CSV is provided in this case | Done — see [`src/pharmas/gsk/log.md`](../src/pharmas/gsk/log.md) |

### Tier 3 — Interactive JS Widget (Network-Tab / Playwright)

The pipeline is rendered dynamically. Data must be extracted from the network tab (XHR/Fetch JSON) or via headless browser.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| J&J | `https://investor.jnj.com/pipeline/development-pipeline/` | Fully JS-rendered widget with drug-name search. Check network tab for underlying API call. PDF available as well | TODO |
| Eli Lilly | `https://lilly.com/science/research-development/pipeline` | Interactive — click each molecule box to expand. Check network tab for JSON. | TODO |
| Sanofi | `https://sanofi.com/en/our-science/our-pipeline` | Interactive filterable tracker. 77 clinical-stage projects (2026). | TODO |
| Novo Nordisk | `https://novonordisk.com/science-and-technology/r-d-pipeline.html` | Interactive, filterable by phase and therapeutic area. Small pipeline, diabetes/obesity-heavy. | Done — see [`src/pharmas/novonordisk/log.md`](../src/pharmas/novonordisk/log.md) |
| Gilead | `https://gilead.com/science-and-medicine/pipeline` | ~58 clinical-stage programs. DOM may be parseable without full Playwright. | TODO |
| Teva | `https://tevapharm.com/science/pipeline/` | Interactive filterable tracker. Mix of innovative + biosimilars. | TODO |
| CSL | `https://www.csl.com/research-and-development/product-pipeline` | You have to interact to extract the indication. | TODO |
| Merck KGaA | `https://www.merckgroup.com/en/research/healthcare-pipeline.html` | Interactive filterable tracker. | TODO |

### Tier 4 — Narrative Text, No Structured Table

No tabular or JSON-serialised pipeline exists. Information is embedded in prose, requiring manual or NLP-based extraction.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| AbbVie | `https://www.abbviescience.com/en/pipeline.html` | Narrative text per therapeutic area. Individual trials link out to ClinicalTrials.gov. No single structured source. | TODO |

## Strategy (High-Level)

Detailed strategy discussions are tracked as **GitHub Issues** in this repository. High-level approach:

1. **Start with Tier 1** — build the pipeline ingestion pipeline on the cleanest sources first (Pfizer, AZ, Novartis, Roche, BI, Takeda). Validate parsing with pdfplumber / Camelot.
2. **Tier 2** — adapt parsers for chart-style PDFs (Amgen, Merck & Co.) and semi-structured documents (BMS, Bayer). May require OCR fallback (pytesseract).
3. **Tier 3** — inspect network-layer calls for each JS widget to find JSON endpoints; fall back to Playwright for dynamic rendering.
4. **Tier 4** — manual curation or LLM-assisted extraction from narrative text. Lowest priority.

All extracted data should map to the unified schema defined in [`data-model.md`](data-model.md).
