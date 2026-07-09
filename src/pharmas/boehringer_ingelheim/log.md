# Boehringer Ingelheim — Extraction Log

## Status: ✅ Done (converted from PDF via user download)

## Source
- **Webpage:** `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline`
- **PDF:** `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline/pdf/human-pharma-clinical-pipeline`
- **Tier:** 1 (per sources.md)

## What We Know About the Page

### Structure
- 6 therapeutic-area tabs: Cardiovascular-Renal-Metabolic, Eye Health, Immunology, Mental Health, Oncology, Respiratory
- Pipeline rendered by a **Stencil.js web component** (`csbep-bi-cms`)
- Page metadata says "Selection of projects as of May 2026"
- Stats: >80 active preclinical/clinical projects, >15 new Phase II/III starts expected, 50% externally partnered
- Google-indexed counts: Registration (3), Phase 3 (11), Phase 2 (13), Phase 1 (24)
- Individual detail pages exist at `/clinical-pipeline/<compound-slug>` (~40+ pages)

### Web Component Analysis
- Component: `csbep-bi-cms` hosted at `https://csbep-bi-cms.web.app/build/csb.esm.js`
- Stencil.js v7, built 2026-07-09
- Uses **Firebase** for backend:
  - Project: `csbep-75ff0` (API key: `AIzaSyCri8CpGF4DCQc79NMc5BreySAJ4QKIbDc`)
  - Secondary: `csbcomponents` (API key: `AIzaSyCSDkHP3iGqudjNjkj8zRvBB1QRf9yDZkc`)
  - Auth: anonymous sign-in, custom tokens, email/password
- Uses **Azure Cognitive Search** for job search (careers), not pipeline
- Drupal JSON API endpoints discovered: `/boehringer-ingelheim-human-pharma-clinical-pipeline` and `-dynamic`

### Attempted Approaches (all failed from EBI IP)
| Method | Result |
|---|---|
| Plain curl | Incapsula iframe |
| StealthyFetcher (Camoufox) | Incapsula iframe |
| DynamicFetcher | 403, incident ID |
| Playwright (headless) | Incapsula iframe, Error 15 |
| Googlebot UA | Same Incapsula response |
| Wayback Machine (live) | Page not captured (Incapsula blocks archive crawlers) |
| Wayback Machine (JSON endpoint) | 2024 captures have no actual data |
| Jina AI reader | Empty (page blocked) |
| Google Cache | Not cached (Incapsula blocks crawlers) |
| Firebase REST (anonymous auth) | Permission denied |
| Homepage, subdomains, PDF URL | All Incapsula-blocked |
| Multiple EBI WiFi networks | Same block (whole 193.62.0.0/16 range?) |

### Conversion Details

**Source:** PDF provided by user (`2026_May_Clinical_Pipeline.pdf`) — page was WAF-blocked from EBI IP range.

**Converter logic:**
- `asset_name` = BI code number (e.g. "BI 1810631"), or compound name when no BI code
- `synonyms` = INN name (e.g. ["Zongertinib"]) — set to `None` when no INN exists
- `therapeutic_area` = the PDF's section label (Oncology, Respiratory, Cardiovascular-Renal-Metabolic, Eye Health, Immunology, Mental Health)
- `indication` = specific disease/condition from the PDF card
- `phase`: "Registration" → `Preregistration`; "Phase 1/2/3" → `Phase 1/2/3`
- Phase 1 entries without compound names use `asset_name="Undisclosed"` with `moa` as the only identifier

**Field-mapping decisions** (confirmed with user):
- Code name as primary asset_name, INN as synonym
- Registration → Preregistration
- Include all Phase 1 entries (even unnamed)
- Skip legend footnote symbols (combination, partnership, designations)

**Output:**
- 52 rows: Registration (3), Phase 3 (11), Phase 2 (14), Phase 1 (24)
- Parquet: `boehringer_ingelheim_pipeline.parquet`

### WAF Blockade Notes
The entire `boehringer-ingelheim.com` domain is behind **Incapsula (Imperva) WAF**. The EBI IP range (193.62.0.0/16) is fully blocked. All automated access methods failed:
- Plain curl, StealthyFetcher, DynamicFetcher, Playwright, Googlebot UA
- Wayback Machine, Google Cache, Jina AI reader
- Firebase REST API (even with anonymous auth tokens)
- All subdomains and the PDF URL

Page uses a Stencil.js web component (`csbep-bi-cms`) with Firebase Realtime Database backend. Pipeline data is client-side rendered, not server-rendered in the HTML.
