# Johnson & Johnson — Mapping log

## Source

- **Pipeline page:** <https://investor.jnj.com/pipeline/development-pipeline/>
- **Data source:** Playwright scrape of the JS-rendered Q4 Web Platform widget (behind Cloudflare — raw curl returns 403). The page renders all 100 pipeline indications into the DOM after JS execution.
- **Actual tier:** Tier 3 (Cloudflare-gated JS widget confirmed; PDFs also available but show only quarterly changes, not the full pipeline)
- **Extraction date:** 2026-07-09

## Field mapping

| PipelineRecord field | Source field | Notes |
|---|---|---|
| `company` | — | Hard-coded "Johnson & Johnson" |
| `asset_name` | Text extracted from each pipeline card | Compound code from parenthetical (e.g. `daratumumab` from "DARZALEX (daratumumab)", `niraparib/abiraterone` from "AKEEGA (niraparib/abiraterone)"). For entries without a parenthetical code (e.g. "Bleximenib", "pasritamig"), the full name is used. |
| `synonyms` | Brand name | Extracted from the portion before the parenthetical (e.g. "DARZALEX", "AKEEGA"). |
| `indication` | Indication text from the card | Usually includes the trial name in parentheses (e.g. "Frontline Multiple Myeloma TNI (CARTITUDE-5)"). |
| `therapeutic_area` | Page section header | One of Oncology, Immunology, Neuroscience, or None (for "Select Other Areas" entries). |
| `phase` | Phase label from the card | `Phase 1` → Phase 1, `Phase 2` → Phase 2, `Phase 3` → Phase 3, `Registration` → Preregistration. |

## Data-quality observations

1. **100 pipeline indications** extracted, matching the "100 of 100 total indications" counter on the page.
2. **No mechanism of action** — the J&J pipeline page does not disclose MoA for pipeline assets.
3. **No modality** — not available in the source.
4. **Some assets have multiple indications** at different phases (e.g. CARVYKTI in Phase 3 for two frontline myeloma indications).
5. **"Select Other Areas"** entries (CABENUVA, UPTRAVI, macitentan, milvexian, SIRTURO — 7 entries) have `therapeutic_area` set to None since they span multiple areas.
6. **Registration is the source term for preregistration submissions** — mapped to Preregistration in the shared schema.
7. **The quarterly PDF** (`JNJ-Pipeline-1Q26.pdf`) is a changes-only document showing Added/Advanced/Removed assets, not a full pipeline snapshot. The JS widget has the complete data.
