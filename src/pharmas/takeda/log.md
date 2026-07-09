# Takeda — extraction log

**Source:** `qr2025_q4_Pipeline_table_en.pdf` downloaded from
<https://www.takeda.com/science/pipeline/>

**Pipeline date:** Q4 FY2025 (ending March 31, 2026)

**Converter:** `takeda_to_parquet.py`

## Mapping decisions

| PDF column | Schema field | Notes |
|---|---|---|
| Development code | `asset_name` | TAK/SGN code. Footnote markers (*1, etc.) stripped. |
| <generic name> | `synonyms` | Inside angle brackets on the same or adjacent line. |
| Brand name(s) | `synonyms` | Multiple brands (e.g., ADYNOVATE / ADYNOVI) all listed. |
| Type of Drug (administration route) | `mechanism_of_action` | Injection/oral/subcutaneous route stripped from MoA string. |
| Modality | `modality` | e.g., "Small molecule", "Biologic and other", "Peptide/oligo- nucleotide". |
| Indications / additional formulations | `indication` | Multi‑row fragments merged by span‑based heuristic. |
| Country/Region | Not mapped separately | Folded into `indication` in earlier versions; now unused. |
| Stage | `phase` | Approved→Registered, Filed→Preregistration, P‑III→Phase 3, P‑II→Phase 2, P‑I→Phase 1. |

## Extraction approach

Position‑aware word extraction (`pdfplumber.extract_words`) because the PDF table
spans multiple fragmented rows per asset. Rows are grouped into **blocks** by
dev‑code; within each block, stage rows are identified and their **span**
(rows between consecutive stage rows) is collected as the indication text.

## Data‑quality observations

1. **Excellent** — most indications are complete and correctly paired with
   their stage. Multi‑row fragments (e.g. "…treatment of … von Willebrand
   disease" split across two word‑rows) are reassembled.

2. **TAK‑577** — the PDF has two distinct indications
   ("Pediatric on‑demand…" and "Pediatric prophylactic…") with multiple stages
   each. The span heuristic correctly separates them, but the on‑demand P‑III
   (surgery) entry is merged into the single Registered entry (same indication
   text, different stage). Acceptable — the stage is captured in `phase`.

3. **TAK‑961** — Two "Multiple Indications / Registered" entries (Feb 2025 and
   July 2025) are deduplicated since they share the same `(asset, indication,
   phase)` tuple. The distinct Japanese approval dates are not captured in the
   current schema.

4. **TAK‑330** — The "Coagulation Disorder" and "(DOAC) reversal" parts of the
   same indication were on separate spans and have been merged by the substring
   dedup. One merged entry remains.

5. **TAK‑771 / TAK‑881 / TAK‑411** — Long indication strings
   ("…polyradiculoneuropathy and multifocal motor neuropathy") that were spread
   across multiple PDF rows are correctly reconstructed.

6. **Footnotes** — Footnote references (`*1`–`*7`) are stripped from asset
   names and stored in `notes`. Partnership details are available via the
   `source_url`.

## Missing

- Separate regional entries for the same (asset, phase) — Japan/U.S./EU filings
  for TAK‑861's "Narcolepsy type 1" are deduplicated. The schema does not
  distinguish by region.
- TAK‑495 has a placeholder `-` as indication (no named indication in the PDF).

## Extraction date

2026-07-09
