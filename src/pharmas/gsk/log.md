# GSK pipeline — extraction log

Date: 2026-07-08
Source: https://www.gsk.com/en-gb/innovation/pipeline#our-pipeline (`1q2026-pipeline-list.xlsx`, sheet `1Q2026-Pipeline`, 76 rows)

Tier 2 per `docs/sources.md` ("CSV is provided in this case" — xlsx here, same idea: no
PDF parsing needed, structured table straight from the source).

## 1. Schema mapping decisions (confirmed with user, following the Roche precedent — see `pharmas/roche/log.md`)

- `asset_name` = `Compound Number` column always (e.g. `GSK2330672`). No `"CHU"`-style
  placeholder collisions in this source — every row has a real compound code.
- `synonyms` (extra field): array of non-empty `INN / Generic Name` / `Brand Name`
  values, deduped, excluding anything equal to `asset_name`.
- `mechanism_of_action`: GSK's xlsx has a dedicated `Mode of Action / Vaccine Type`
  column (unlike Roche, which required regex extraction from free text) — mapped
  directly, `null` when blank. 0/76 rows null.
- `therapeutic_area`: kept verbatim from CSV (`HIV (ViiV)`, `Infectious Diseases`,
  `Oncology`, `Respiratory, Immunology and Inflammation`) — same "no cross-company
  normalisation yet" decision as Roche.
- `phase`: `Phase I/II/III` map 1:1 to `Phase 1/2/3`. `Registration` maps to
  `Preregistration` (not `Registered`) — user's call: GSK's pipeline page uses
  "Registration" for assets filed/under review, not yet approved, same semantic slot
  as Roche's `Filed`. (No `Preclinical`, `Phase 1/2`, `Phase 2/3`, `Registered`, or
  `Discontinued` values present in this source.)
- `trial_id`: always `null` — no NCT identifiers in the source.
- `source_url`: constant, `https://www.gsk.com/en-gb/innovation/pipeline#our-pipeline`.
- `extraction_date`: `2026-07-08`, the date the xlsx was downloaded.
- `notes`: left `null` — extras go to `others` instead.
- `others` (extra field): array of `"Key: value"` strings built from `In-license or
  other alliance relationship with third party`, `Footnotes`, `Reviewed and final` —
  only non-empty values included.

## 2. Known data-quality issue in the source (not fixed, flagged only)

One row has `Indication` and `Mode of Action / Vaccine Type` apparently transposed:
`GSK6775388` (ozureprubart) has `Indication="anti-IgE antibody"` and
`Mode of Action="Food allergies"` — clearly swapped (ozureprubart is an anti-IgE
antibody; food allergy is the disease it targets). Loaded as-is per the same
load-as-is-and-flag policy used for Roche's transposed rows.

## 3. Output

`pharmas/gsk/schema.py` — same Pydantic `PipelineRecord` model + `Phase` enum as Roche.
`pharmas/gsk/gsk_xlsx_to_parquet.py` — xlsx → parquet converter.
`pharmas/gsk/gsk_pipeline.parquet` — 76 rows, one per (company, asset, indication).

Run: `uv run python pharmas/gsk/gsk_xlsx_to_parquet.py`
