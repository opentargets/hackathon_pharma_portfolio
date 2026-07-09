# Novartis Pipeline — Extraction Log

## Summary

- **Source**: `https://www.novartis.com/research-development/novartis-pipeline`
- **Tier**: Tier 1 (server-rendered HTML via Drupal View, paginated across 6 pages, no JS needed despite AJAX filter forms)
- **Row count**: 106 compound–indication pairs (61 unique compound codes)
- **Fetched**: 2026-07-09
- **Tooling**: `requests` + `BeautifulSoup` (no Playwright needed)

## Source Inspection

`docs/sources.md` listed Novartis as Tier 1 ("Quarterly PDF linked from pipeline page"). We checked both options:

1. **PDF**: `/sites/novartis_com/files/novartis-pipeline-2025-annual-report.pdf` — 3-page extract from the 2025 Annual Report (Feb 2026). Table covers only ~30 "Selected development projects" in Confirmatory Development (Phase II → Registration). Excludes Phase I and many Phase II compounds. Also includes a "Projects removed" table on page 3. Columns: Compound/Common name, MoA, Potential indication, Category, Route, Year entered phase, Filing dates/phase.

2. **Live webpage**: The Drupal View (`view-id: compounds_list`) renders the full pipeline table server-side in the initial HTML as `.pipeline-main-wrapper` divs. 6 pages × 20 items ≈ 106 total rows. No JS interaction needed — the AJAX pagination links are only required for multi-page navigation. Fields: compound_name, generic_name, indication_name, therapeutic_area, phase, filing_date, mechanism_of_action, indication_type.

**Decision**: Used the webpage (106 rows, includes Phase 1 through Registration, full pipeline coverage). The PDF covers fewer rows and only late-stage — not used.

## Data Quality

### Anomalies

- **8 rows lack `mechanism_of_action`**: All early-phase (Phase 1–2) compounds with compound codes only (no branded/INN name). Examples: EDK060, GCJ904, GHZ339, HJB647, IPX643, OJR520, QCZ484, YMI024. These are genuinely undisclosed — left as `null`.
- **21 rows lack `indication_type`**: These are early-phase compounds where the indication hasn't been classified as Lead/Supplementary/New. Left as `null` in `others`.
- **36 rows have `generic_name` == `compound_code`**: No brand/INN name available for these assets. `synonyms` is `null` for these.
- **2 rows with `therapeutic_area` = "Others"**: LNP023 (Fabhalta) / iAMD and PAC001 / Thyroid eye disease (TED). Kept verbatim as the source's own classification.

### Cross-check

Manual copy/paste of 8 rows from the live page (across Registration, Phase 3, Phase 2, Phase 1 phases) was diffed against the parquet output. **100% match** — no inconsistencies found.

## Field Mapping

| Schema field | Source field | Notes |
|---|---|---|
| `company` | — | Hardcoded "Novartis" |
| `asset_name` | `compound_name` | Compound code (e.g. "AAA601", "AIN457"). Per confirmed preference (2026-07-08 AZ convention): compound code over brand name. |
| `synonyms` | `generic_name` | Brand/INN name (e.g. "Lutathera", "ianalumab") with ® suffix stripped. Only set when generic_name differs from compound_code. |
| `mechanism_of_action` | `mechanism_of_action` | Direct mapping. 8 rows left null (source doesn't disclose). |
| `therapeutic_area` | `therapeutic_area` | Kept verbatim from source. No normalization yet (deferred until more companies loaded). |
| `indication` | `indication_name` | Direct mapping. |
| `phase` | `phase` | Phase 1→Phase 1, Phase 2→Phase 2, Phase 3→Phase 3, Registration→Preregistration. "Registration" on Novartis's site means a marketing application has been submitted ("under review"), not yet approved. |
| `trial_id` | — | Not available from source. Left as `null`. |
| `source_url` | — | Hardcoded to the live pipeline page URL. |
| `extraction_date` | — | 2026-07-09 |
| `others` | `indication_type`, `filing_date` | Stored as "Indication type: {Lead/Supplementary/New}" and "Planned filing: {date}" strings in the `others` array. 85/106 rows have at least one entry. |

## Files

| File | Description |
|---|---|
| `__init__.py` | Empty, makes this a subpackage |
| `scrape_pipeline.py` | Fetches all 6 pages, parses `.pipeline-main-wrapper` divs into raw JSON/CSV |
| `raw_pipeline.json` | Unmapped scraped data (106 rows, 8 fields) |
| `raw_pipeline.csv` | Same data in CSV format |
| `novartis_to_parquet.py` | Maps raw scraped data to `PipelineRecord` schema, writes parquet |
| `novartis_pipeline.parquet` | Final output (106 rows, 13 columns) |
| `log.md` | This file |
