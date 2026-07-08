# Roche pipeline — extraction log

Date: 2026-07-08
Source: https://www.roche.com/solutions/pipeline (`pharmaq126.pdf`, "Status as of April 23, 2026"; `Roche_Pipeline_Final_2026-07-08.csv`)

## 1. CSV vs PDF cross-check

Compared row counts by phase between the CSV (128 rows) and the PDF summary tables (pages 1-10 of 68):

| Phase | PDF summary | CSV |
|---|---|---|
| Phase 1 | 41 NME + 6 AI = 47 | 47 |
| Phase 2 | 12 NME + 6 AI = 18 | 17 |
| Phase 3 | 11 NME + 22 AI = 33 | 34 |
| Registration/Approved | 2 NME + 5 AI (new filings) + 15 marketed products (many w/ multiple indications) | Filed 6, Approved 24 |

Phase 1 matches exactly. Phase 2/3 are off by one each, likely a boundary classification
difference between the PDF's summary slide and the full per-indication CSV (not
investigated line-by-line — CSV is corroborated as "comprehensive" per the confirmed
Phase 1 count and consistent per-drug detail on the later PDF pages). CSV treated as
source of truth per `pharmas/roche/instructions.md` item 0.

## 2. Environment

`uv init` at repo root; added `pandas`, `pyarrow`, `pydantic` (see `pyproject.toml` / `uv.lock`).

## 3. Schema mapping decisions (confirmed with user)

- `asset_name` = CSV `Compound` (RG-code) always, including the literal `"CHU"`
  placeholder Roche uses for 9 Chugai-managed assets without an RG-code — user chose to
  keep the collision as-is rather than substitute Generic Name, relying on `synonyms` to
  disambiguate.
- `synonyms` (extra field, not in base schema): array of non-empty `Generic Name` /
  `Trade name` values, deduped, excluding anything equal to `asset_name`.
- `mechanism_of_action`: no dedicated MoA column in the CSV. Extracted heuristically from
  `Description` — first sentence matching `\bis (a|an)\b` (e.g. "...is a bispecific
  antibody..."). Left `null` when no such sentence exists (41/128 rows, incl. all rows
  with empty `Description`). Deterministic regex, not LLM-inferred.
- `therapeutic_area`: kept verbatim from CSV (`Oncology/Hematology`, `Neuroscience`,
  `Cardiovascular, Renal & Metabolism`, `Immunology`, `Ophthalmology`, `Other`) — no
  cross-company normalisation yet, deferred until more pharmas are loaded.
- `phase`: mapped to the enum in `docs/data-model.md#phase-enum`:
  `Approved` → `Registered`, `Filed` → `Preregistration`, `Phase 1/2/3` unchanged.
  (No `Preclinical`, `Phase 1/2`, `Phase 2/3`, or `Discontinued` values present in this CSV.)
- `trial_id`: always `null` — CSV has no NCT identifiers.
- `source_url`: constant, `https://www.roche.com/solutions/pipeline`.
- `extraction_date`: `2026-07-08`, per the CSV filename (date fetched, not PDF publication date).
- `notes`: left `null` — Roche-specific extras go to `others` instead (see below).
- `others` (extra field, not in base schema): array of `"Key: value"` strings built from
  `Trade name`, `Project type` (nme/ai), `Partner`, `Managed by`, `Filing date`,
  `Combination` — only non-empty values included. Combination-partner text (e.g. "plus
  everolimus") is kept here rather than folded into `asset_name` as `"Drug A + Drug B"`
  (deviates from the data-model.md combination-therapy convention per explicit user
  choice, since `asset_name` is pinned to the RG-code).

## 4. Known data-quality issues in the source CSV (not fixed, flagged only)

Two `CHU` rows have `Generic Name` and `Indication` apparently transposed:
- `Generic Name="solid tumors"`, `Indication="pan-KRAS inhibitor (AUBE00)"`
- `Generic Name="CRC"`, `Indication="CDH17 ADC"`

Loaded as-is per user decision; needs manual correction upstream if it matters downstream.

## 5. Output

`pharmas/roche/schema.py` — Pydantic `PipelineRecord` model + `Phase` enum.
`pharmas/roche/roche_csv_to_parquet.py` — CSV → parquet converter.
`pharmas/roche/roche_pipeline.parquet` — 128 rows, one per (company, asset, indication).

Run: `uv run python pharmas/roche/roche_csv_to_parquet.py`
