---
title: Sources
nav_order: 2
---


## Sources by Tier

### Tier 1 — Clean PDF, Stable URL, Machine-Readable Table

PDFs with a clear tabular layout, and full pipeline coverage (including early phase).

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Pfizer | `https://www.pfizer.com/science/drug-product-pipeline` | Quarterly PDF. Columns: Compound / MoA / Indication / Phase / Submission Type | ✅ |
| AstraZeneca | `https://www.astrazeneca.com/our-therapy-areas/pipeline.html` | Server-rendered HTML (no JS needed). Fields: Name, Mechanism, Area under investigation, Phase, Molecule size. PDF also exists but is older (Feb vs Apr 2026) and less rich. See [`src/pharmas/astrazeneca/log.md`](../src/pharmas/astrazeneca/log.md) | ✅ |
| Novartis | `https://www.novartis.com/research-development/novartis-pipeline` | Server-rendered HTML (Drupal View, 6 pages, no JS needed). See [`src/pharmas/novartis/log.md`](../src/pharmas/novartis/log.md) | ✅ |
| Roche | `roche.com/solutions/pipeline` | Semi-annual (H1/H2) | ✅ |
| Boehringer Ingelheim | `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline` | **WAF-blocked** — Incapsula (Imperva) blocks all automated access from EBI IP range. The page is JS-rendered (Stencil.js web component `csbep-bi-cms` + Firebase backend). Google-indexed snippets show substantial pipeline data (Reg 3, P3 11, P2 13, P1 24). Detail pages indexed: ~40+ individual compound pages. WIP — see [`src/pharmas/boehringer_ingelheim/log.md`](../src/pharmas/boehringer_ingelheim/log.md) | 🚧 |
| Takeda | `takeda.com/science/pipeline/` → "DOWNLOAD THE PDF" | Full pipeline PDF. Position-aware word extraction used — table extraction was unreliable due to merged cells. See [`src/pharmas/takeda/log.md`](../src/pharmas/takeda/log.md) | ✅ |

### Tier 2 — PDF Available but with Parsing Caveats

PDFs exist but may be chart-style layouts, exclude Phase 1, or cover only late-stage assets.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| Amgen | `https://www.amgenpipeline.com/` | Static HTML has no data, but the page's own JS calls a plain unauthenticated GET endpoint (`/pipeline/molecule/getjsondata`) that returns the full dataset — no browser needed. Quarterly PDF ("Download Pipeline Chart") covers the same molecules but its Phase column is graphical, not text; JSON used instead. See [`src/pharmas/amgen/log.md`](../src/pharmas/amgen/log.md) | Done |
| Merck & Co. | `https://www.msd.com/research/product-pipeline/` | PDF also available but is a "chart" (positional grid, not a table); the live pipeline page is static HTML with richer per-indication data (MoA, NCT IDs) and was used as primary source instead. Phase 1 candidates not shown. | ✅ |
| BMS | `https://www.bms.com/research-and-development/pipeline.html` | Live HTML pipeline page. Compound + indication pairs per area, not a strict table. Excludes collaborations. No pipeline PDF/CSV exists — data is embedded static JSON in a hidden `<div id="pipeline-data">`, no browser needed. See [`src/pharmas/bms/log.md`](../src/pharmas/bms/log.md) | Done |
| Bayer | `https://www.bayer.com/en/pharma/development-pipeline` | Bot-blocks plain HTTP clients (needs a browser fetcher). 30-row live table merged with a Feb 2026 investor-relations PDF for NCT IDs/completion/status + 9 PDF-only rows. See [`src/pharmas/bayer/log.md`](../src/pharmas/bayer/log.md) | Done |
| GSK | `gsk.com/en-gb/innovation/pipeline` |  CSV is provided in this case | ✅ |
| Gilead | `https://gilead.com/science-and-medicine/pipeline` | **Downgraded from Tier 3.** The underlying Sitecore SXA search API (`/sxa/search/results/` with page-specific query params) returns JSON via plain curl — no browser needed. 50 clinical-stage programs. See [`src/pharmas/gilead/log.md`](../src/pharmas/gilead/log.md) | ✅ |
| Teva | `https://tevapharm.com/science/pipeline/` | **Downgraded from Tier 3.** Static server-rendered HTML (JS filtering is cosmetic CSS show/hide). 24 pipeline rows (biosimilars + innovative). See [`src/pharmas/teva/log.md`](../src/pharmas/teva/log.md) | ✅ |

### Tier 3 — Interactive JS Widget (Network-Tab / Playwright)

The pipeline is rendered dynamically. Data must be extracted from the network tab (XHR/Fetch JSON) or via headless browser.

| Company | Pipeline Source | Notes | Status |
|---|---|---|---|
| J&J | `https://investor.jnj.com/pipeline/development-pipeline/` | Cloudflare-gated Q4 Web Platform widget. Playwright bypasses Cloudflare and renders all 100 indications. See [`src/pharmas/johnson_johnson/log.md`](../src/pharmas/johnson_johnson/log.md) | ✅ |
| Eli Lilly | `https://lilly.com/science/research-development/pipeline` | AEM Edge Delivery site with protected internal API (`/v1/cdp-data`). Playwright network interception captures the JSON. 76 molecules (Phase 2+). See [`src/pharmas/lilly/log.md`](../src/pharmas/lilly/log.md) | ✅ |
| Sanofi | `https://sanofi.com/en/our-science/our-pipeline` | Interactive filterable tracker. 77 clinical-stage projects (2026). | ✅ |
| Novo Nordisk | `https://novonordisk.com/science-and-technology/r-d-pipeline.html` | Interactive, filterable by phase and therapeutic area. Small pipeline, diabetes/obesity-heavy. | ✅ |
| CSL | `https://www.csl.com/research-and-development/product-pipeline` | **Downgraded from Tier 3.** Fully static HTML — "you have to interact" note was stale; `curl` returns all 34 pipeline items including the popup content. No PDF/CSV exists. See [`src/pharmas/csl/log.md`](../src/pharmas/csl/log.md) | Done |
| Merck KGaA | `https://www.merckgroup.com/en/research/healthcare-pipeline.html` | Interactive filterable tracker. | TODO |
| AbbVie | `https://www.abbvie.com/science/pipeline.html` | Cloudflare-gated (plain `curl` gets 403), but once fetched via browser the data is fully static HTML — 57 assets / 97 asset-indication rows embedded as `data-*` attributes, no click-to-reveal needed. No PDF/CSV exists. Devices (6 aesthetics assets) use a distinct phase scale (Concept/Feasibility/Development/Confirmation/Approved/Launched) mapped onto the shared Phase enum. | Done — see [`src/pharmas/abbvie/log.md`](../src/pharmas/abbvie/log.md) |


## Strategy (High-Level)

Detailed strategy discussions are tracked as **GitHub Issues** in this repository. High-level approach:

1. **Start with Tier 1** — build the pipeline ingestion pipeline on the cleanest sources first (Pfizer, AZ, Novartis, Roche, BI, Takeda). Validate parsing with pdfplumber / Camelot.
2. **Tier 2** — adapt parsers for chart-style PDFs (Amgen, Merck & Co.) and semi-structured documents (BMS, Bayer). May require OCR fallback (pytesseract).
3. **Tier 3** — inspect network-layer calls for each JS widget to find JSON endpoints; fall back to Playwright for dynamic rendering.

All extracted data should map to the unified schema defined in [`data-model.md`](data-model.md).
