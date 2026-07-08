# Pfizer — extraction log

Tier 1 in `docs/sources.md` (quarterly PDF, clean table). Source page:
`https://www.pfizer.com/science/drug-product-pipeline`.

## Source

Used the **quarterly PDF** (Q1 2026, as of May 5, 2026) downloadable from the
pipeline page:

`https://cdn.pfizer.com/pfizercom/product-pipeline/Q1%202026%20Pipeline%20Update_vFinal_0.pdf`

The PDF is a genuine machine-readable 5-column table covering all 4 therapeutic
areas across 19 pages (data on pages 5–15). The live webpage was also checked:
it uses a JS-heavy Drupal 10 interactive widget (Canvas-based immersive viewer)
loading data dynamically — no embedded JSON blob or open API endpoint was found.
The PDF was the deterministic source.

## Pipeline snapshot (PDF page 4)

| Phase | Count |
|---|---|
| Phase 1 | 35 |
| Phase 2 | 25 |
| Phase 3 | 31 |
| Registration | 5 |
| **Total** | **96** |

## Converter notes

- **pdfplumber** extracts the 5-column table (`Compound Name | Mechanism of
  Action | Indication | Phase of Development | Submission Type`) cleanly for
  most pages. The Vaccines page (page 14) needed a word-coordinate-based parser
  because the table borders for columns 1–3 are incomplete. Continuation lines
  (multi-line cells) are attributed to the nearest anchor row by `top`
  proximity.
- **Page 15** (discontinued programs, 7 rows) is skipped — only current
  pipeline candidates are exported.
- **Trademark symbols** (`®`/`™`) are stripped from compound names.
- **`►` prefix** (indicating new/progressed since last update) is silently
  removed.
- **Submission Type** (New Molecular Entity / Product Enhancement) is stored in
  `others` as `"Submission Type: ..."`.

## Field-mapping decisions

| Schema field | Source column | Notes |
|---|---|---|
| `company` | — | Hardcoded to `"Pfizer"` |
| `asset_name` | Compound Name | Trademark symbols stripped |
| `mechanism_of_action` | Mechanism of Action | Explicit column, used directly |
| `therapeutic_area` | Section heading | Inferred from which section page the row appears on: I&I (pages 5–6), Internal Medicine (pages 7–8), Oncology (pages 9–13), Vaccines (page 14) |
| `indication` | Indication | Left verbatim including trial names, population descriptors, and regulatory designations |
| `phase` | Phase of Development | Mapped: `Phase 1`→`Phase 1`, `Phase 2`→`Phase 2`, `Phase 3`→`Phase 3`, `Registration`→`Preregistration` |
| `modality` | Inferred | Parsed from `(Biologic)` in indication text → `Biologic`; Vaccines section → `Vaccine`; anything else → `Small Molecule` |
| `trial_id` | — | Not available in the PDF (set to `None`) |
| `source_url` | — | `https://www.pfizer.com/science/drug-product-pipeline` |
| `extraction_date` | — | `2026-07-08` |
| `notes` | — | Not used |
| `others` | Submission Type | Stored as `"Submission Type: New Molecular Entity"` / `"Submission Type: Product Enhancement"` |
| `others` | Modality | Stored as `"Modality: Biologic"` / `"Modality: Small Molecule"` / `"Modality: Vaccine"` |

## Row counts (verification)

- **96 rows** total, matching the PDF's own snapshot precisely.
- Phase breakdown matches the PDF: Phase 1 = 35, Phase 2 = 25, Phase 3 = 31,
  Preregistration = 5.
- Therapeutic area breakdown: I&I = 21, Internal Med = 14, Oncology = 51,
  Vaccines = 10 — all matching the per-section project counts in the PDF.

## Data-quality notes

- The Vaccines page table has incomplete border lines for columns 1–3; the
  word-coordinate fallback parser correctly reconstructs all 10 rows.
- Some compound names are long (e.g. `sigvotatug vedotin (PF- 08046047)`)
  — note the space in `PF- 08046047` is from a PDF line-break artifact
  (kept as-is).
- Modality inference for Internal Medicine: many GLP-1 receptor agonists in
  Phase 1 are labelled `(Biologic)` in the indication, correctly assigned.

## Files

- `Q1_2026_Pipeline_Update.pdf` — original quarterly PDF (19 pages, 415 KB).
- `pfizer_to_parquet.py` — converter (pdfplumber-based).
- `pfizer_pipeline.parquet` — 96 records.
- `__init__.py` — empty subpackage marker.

## Schema change

Added `modality: Optional[str]` field to `PipelineRecord` in `src/schema.py` to
capture compound modality (Biologic / Small Molecule / Vaccine).
