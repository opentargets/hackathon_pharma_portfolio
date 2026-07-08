
## Sources by Tier

### Tier 1 — Clean PDF, Stable URL, Machine-Readable Table

PDFs with a clear tabular layout, and full pipeline coverage (including early phase).

| Company | Pipeline Source | Notes |
|---|---|---|
| Pfizer | `https://www.pfizer.com/science/drug-product-pipeline` | Quarterly PDF. Columns: Compound / MoA / Indication / Phase / Submission Type |
| AstraZeneca | `https://www.astrazeneca.com/our-therapy-areas/pipeline.html` | Annual PDF. Columns: Compound / Mechanism / Area Under Investigation |
| Novartis | `novartis.com/research-development/novartis-pipeline` → PDF | Quarterly PDF linked from pipeline page |
| Roche | `assets.roche.com/f/176343/x/[hash]/pharma{HY}{YY}.pdf` | Semi-annual (H1/H2). Hash in URL — fetch current link from `roche.com/solutions/pipeline` |
| Boehringer Ingelheim | `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline` | Stable URL |
| Takeda | `takeda.com/science/pipeline/` → "DOWNLOAD THE PDF" | Full pipeline PDF + oncology-specific PDF at `takedaoncology.com/science/pipeline/` |

### Tier 2 — PDF Available but with Parsing Caveats

PDFs exist but may be chart-style layouts, exclude Phase 1, or cover only late-stage assets.

| Company | Pipeline Source | Notes |
|---|---|---|
| Amgen | `amgenpipeline.com/-/media/.../amgen-pipeline-chart.pdf` | Quarterly PDF described as a "chart" — likely vector-based, not a literal table. |
| Merck & Co. | `https://www.msd.com/research/product-pipeline/` | PDF also available. "chart." Phase 1 candidates not shown. |
| BMS | `https://annual-report.bms.com/assets/bms-ar/documents/2025/2025-bms-development-portfolio.pdf` | Annual PDF only. Compound + indication pairs per area, not a strict table. Excludes collaborations. |
| Bayer | `bayer.com/en/pharma/development-pipeline` → downloadable "overview package" | ~30 late-stage projects only (not full pipeline). |
| GSK | `gsk.com/en-gb/innovation/pipeline` |  CSV is provided in this case |

### Tier 3 — Interactive JS Widget (Network-Tab / Playwright)

The pipeline is rendered dynamically. Data must be extracted from the network tab (XHR/Fetch JSON) or via headless browser.

| Company | Pipeline Source | Notes |
|---|---|---|
| J&J | `investor.jnj.com/pipeline/development-pipeline` | Fully JS-rendered widget with drug-name search. Check network tab for underlying API call. PDF available as well |
| Eli Lilly | `lilly.com/science/research-development/pipeline` | Interactive — click each molecule box to expand. Check network tab for JSON. |
| Sanofi | `sanofi.com/en/our-science/our-pipeline` | Interactive filterable tracker. 77 clinical-stage projects (2026). |
| Novo Nordisk | `novonordisk.com/science-and-technology/r-d-pipeline.html` | Interactive, filterable by phase and therapeutic area. Small pipeline, diabetes/obesity-heavy. |
| Gilead | `gilead.com/science-and-medicine/pipeline` | ~58 clinical-stage programs. DOM may be parseable without full Playwright. |
| Teva | `tevapharm.com/science/pipeline/` | Interactive filterable tracker. Mix of innovative + biosimilars. |
| CSL | `csl.com/research-and-development/product-pipeline` | You have to interact to extract the indication. |
| Merck KGaA | `https://www.merckgroup.com/en/research/healthcare-pipeline.html` | Interactive filterable tracker. |

### Tier 4 — Narrative Text, No Structured Table

No tabular or JSON-serialised pipeline exists. Information is embedded in prose, requiring manual or NLP-based extraction.

| Company | Pipeline Source | Notes |
|---|---|---|
| AbbVie | `abbviescience.com/en/pipeline.html` | Narrative text per therapeutic area. Individual trials link out to ClinicalTrials.gov. No single structured source. |

## Strategy (High-Level)

Detailed strategy discussions are tracked as **GitHub Issues** in this repository. High-level approach:

1. **Start with Tier 1** — build the pipeline ingestion pipeline on the cleanest sources first (Pfizer, AZ, Novartis, Roche, BI, Takeda). Validate parsing with pdfplumber / Camelot.
2. **Tier 2** — adapt parsers for chart-style PDFs (Amgen, Merck & Co.) and semi-structured documents (BMS, Bayer). May require OCR fallback (pytesseract).
3. **Tier 3** — inspect network-layer calls for each JS widget to find JSON endpoints; fall back to Playwright for dynamic rendering.
4. **Tier 4** — manual curation or LLM-assisted extraction from narrative text. Lowest priority.

All extracted data should map to the unified schema defined in [`data-model.md`](data-model.md).
