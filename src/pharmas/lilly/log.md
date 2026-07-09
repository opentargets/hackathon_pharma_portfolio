# Eli Lilly — Mapping log

## Source

- **Pipeline page:** <https://lilly.com/science/research-development/pipeline>
- **Data source:** Playwright network interception of the internal API (`https://edg-api.unex.lilly.com/v1/cdp-data`). The page is a fully JS-rendered AEM Edge Delivery site — the API is internal/protected but Playwright captures the response when the browser renders the page.
- **Actual tier:** Tier 3 (confirmed — JS widget with protected API)
- **Extraction date:** 2026-07-09

## Field mapping

| PipelineRecord field | API field | Notes |
|---|---|---|
| `company` | — | Hard-coded "Eli Lilly" |
| `asset_name` | `title` | Molecule name (e.g. "Imlunestrant", "Tirzepatide", "Orforglipron"). Stripped of trailing whitespace. |
| `indication` | `indication` | Primary indication from the API (e.g. "Adjuvant Breast Cancer", "Diabetes"). |
| `therapeutic_area` | `therapeutic_area_id` → `therapeutic_area_by_id` | Mapped via the API's `therapeutic_area_by_id` lookup: 324→Cancer, 325→Immunology, 326→Cardiometabolic Health, 327→Neuroscience. |
| `phase` | `phase` (integer index) | 2→Phase 2, 3→Phase 3, 4→Preregistration ("Regulatory Review"), 5→Registered ("Regulatory Approval Achieved"). |
| `modality` | `modalityTitle` | "Small Molecule" or "Large Molecule". |

## Data-quality observations

1. **76 molecules** extracted — all clinical-stage programs (Phase 2 and later). Phase 1/preclinical are not shown on this page.
2. **No mechanism of action** — not exposed in the API payload.
3. **Phase 1 assets absent** — the API's `phase_titles` includes Phase 1 but no molecules use phase index 1.
4. **`body_html` was checked for multiple indications** per the user's instruction — no multi-indication entries found. Each molecule has a single indication in the API.
5. **Regulatory Approval Achieved** (phase 5) maps to `Registered` — only 1 molecule (likely tirzepatide or a related asset) is in this category.
6. **Some molecules have trailing whitespace** in the `title` field (e.g. "Imlunestrant  "), stripped during conversion.
7. **State titles** (NEW, NAMED, MILESTONE) are informational labels on the page — not mapped to any schema field.
