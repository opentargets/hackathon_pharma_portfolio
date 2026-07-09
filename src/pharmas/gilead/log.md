# Gilead — Mapping log

## Source

- **Pipeline page:** <https://gilead.com/science-and-medicine/pipeline>
- **Data source:** Sitecore SXA search API (`/sxa/search/results/` with query parameters scraped from the page's `data-properties` attribute)
- **Actual tier:** Tier 2 (API accessible via curl — no Playwright needed despite docs marking it Tier 3)
- **Extraction date:** 2026-07-09

## Field mapping

| PipelineRecord field | Source field | Notes |
|---|---|---|
| `company` | — | Hard-coded "Gilead" |
| `asset_name` | `.field-headbrandname` | Full text from the HTML snippet (e.g. "Emvistegrast (SWIFT)"). Includes trial name in parentheses where present. |
| `indication` | `.field-potentialindication` | Specific disease/condition. Falls back to `.field-tagname` (first occurrence / sub-category) when the dedicated indication field is empty. |
| `therapeutic_area` | `.field-therapeuticareaname` | One of Virology, Oncology, Inflammation & Fibrosis. |
| `phase` | `.phase-name.field-tagname` (second occurrence) | `Phase 1` → Phase 1, `Phase 2` → Phase 2, `Phase 3` → Phase 3, `Filed` → Preregistration, `Opt-in Trials` → Phase 3 with `others: ["Phase_note: Opt-in Trials"]` |
| `notes` | `.field-notesdetail` | Free-text annotations (e.g. "Previously GS-1427", breakthrough therapy designations). |

## Data-quality observations

1. **50 clinical-stage programs** returned by the API — close to the ~58 estimate in `docs/sources.md`. The 8 missing are likely preclinical or discovery-stage programs not indexed in this search endpoint.
2. **No mechanism of action** or modality in the source. Both are omitted from the output.
3. **Indications are 50/50 coverage** — every entry has either a specific indication or a sub-category fallback (e.g. "Advanced cancers", "HIV Treatment").
4. **Some compound names include trial names** in parentheses (e.g. "Lenacapavir (PURPOSE 365)"). These were kept as-is since the trial name is part of the compound-indication context.
5. **Opt-in Trials** (3 entries) mapped to Phase 3 with a note in `others`. These are investigator-sponsored or collaborative trials that Gilead supports.
