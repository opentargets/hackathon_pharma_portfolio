# Teva — Mapping log

## Source

- **Pipeline page:** <https://tevapharm.com/science/pipeline/>
- **Data source:** Static server-rendered HTML (no JS widget — the JS filtering is purely cosmetic CSS show/hide)
- **Actual tier:** Tier 2 (static HTML, curl + BeautifulSoup sufficient despite docs marking it Tier 3)
- **Extraction date:** 2026-07-09

## Field mapping

| PipelineRecord field | Source field | Notes |
|---|---|---|
| `company` | — | Hard-coded "Teva" |
| `asset_name` | `.vi-accordion-pipeline__subtitle` (INN or code) | INN or compound code from the subtitle parenthetical (e.g. `denosumab`, `TEV-'574`). For entries without a subtitle, falls back to the title. |
| `synonyms` | `.vi-accordion-pipeline__title` | Brand/reference name (e.g. "Biosimilar to Prolia") stored as synonym when different from asset_name. |
| `indication` | Tags (filtered from `.vi-accordion-pipeline__tag`) | Tags that are NOT `Biosimilars` or `Innovative Medicines` are treated as indications. Multi-indication entries (comma-separated) generate separate rows. |
| `modality` | `style` attribute color | `#00567a` → Biosimilar, `#00a03b` → Novel Biologic, `#00aca8` → Small Molecule. |
| `phase` | Parent `<H3>` section heading | `Approved` → Registered, `Under Regulatory Review` → Preregistration, `Phase 1/2/3` → Phase 1/2/3, `Pre-clinical` → Preclinical. `Clinical` parent heading is skipped (it's a category wrapper, not a phase). |
| `therapeutic_area` | — | Not available. Tags are either drug-type classifiers or indications, not therapeutic areas. |

## Data-quality observations

1. **27 pipeline entries** in the source, split into **24 rows** after deduplication and multi-indication splitting.
2. **Biosimilars dominate** (11/24 rows). These are entries for reference product biosimilars with INN as asset_name.
3. **Duplicate entries are from the source**, not a parsing error — e.g. `golimumab` appears twice under "Under Regulatory Review" with identical data. These may represent different formulations or presentations not distinguished in the source HTML.
4. **No therapeutic area** is exposed for any entry.
5. **Mechanism of action** is not available.
6. **Biosimilar entries** often lack an indication-specific tag — they only have the "Biosimilars" classifier. These produce rows with empty indication.
7. **Smart quotes** in compound codes (e.g. `TEV-'574` with a right single quotation mark) are preserved as-is from the source.
