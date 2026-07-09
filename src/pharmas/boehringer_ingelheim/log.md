# Boehringer Ingelheim — Extraction Log

## Status: 🚧 Blocked by Incapsula WAF

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

### Data Availability (from Google-indexed snippets)
Substantial pipeline data is indexed by Google, including:
- **Registration (3):** Zongertinib (BI 1810631), Nerandomilast (BI 1015550) ×2
- **Phase 3 (11):** Tenecteplase, Vicadrostat+Empagliflozin ×2, Survodutide (BI 456906) ×2, Zongertinib, Obrixtamig (BI 764532), Nerandomilast, plus 3 more from CRM
- **Phase 2 (13):** BI 1815368, BI 764524, BI 1584862, BI 771716, Nerandomilast, Avenciguat (BI 685509), BI 3032950, BI 3000202, Obrixtamig ×2, plus 3 more
- **Phase 1 (24):** Multiple oncology programs including zongertinib combos, ezabenlimab, BI 770371, BI 1701963 (SOS1), BI 905677 (KRAS G12C), DLL3/CD3+SoC, B7-H6/CD3, VSV-GP, STING agonist

### Pipeline Data Structure (from Google)
Each row: Therapeutic Area | Indication | Mechanism | Compound name. Detail pages add: NCT IDs, phase, description.

## Next Steps
- Try from a non-EBI/home IP to access the live page
- Once accessed, extract the rendered HTML (the Stencil component renders the pipeline data client-side)
- Or, if Google-indexed snippets are sufficient, extract all ~50 pipeline entries from search results
