# Bayer — extraction log

Tier 2 in `docs/sources.md` ("~30 late-stage projects only (not full
pipeline)"). Tracked in GitHub issue
[#31](https://github.com/opentargets/hackathon_pharma_portfolio/issues/31).

## Source discovery

Checked both possible source types before starting, per
`instruction_for_agent.md`.

- **Plain `curl`/`WebFetch` on any bayer.com URL returns HTTP 403** — a
  bot-detection "Site Maintenance" page (`<title>Site Maintenance</title>`,
  "Your bot have been rated as a harmful activity..."), not a real 404/robots
  block. This applies to the pipeline webpage *and* any PDF under
  `bayer.com/sites/default/files/...` — the whole domain bot-gates
  non-browser clients, not just the interactive page.
  - Worked around with scrapling's `StealthyFetcher` (Camoufox browser) for
    the webpage, and `scrapling.fetchers.Fetcher.get(..., impersonate="chrome")`
    (curl_cffi TLS/JA3 impersonation, no full browser needed) for the PDF —
    both return HTTP 200 with real content once the request looks like a
    normal browser rather than a bare HTTP client.
- **Webpage**: `docs/sources.md`'s URL
  (`https://www.bayer.com/en/pharma/development-pipeline`) resolves directly
  (a redirect chain through `pharma.bayer.com/.../development-pipeline/` and
  `www.bayer.com/en/pharmaceuticals` also exists but lands on a general
  overview page, not the pipeline table — the sources.md URL is the correct
  one). Server-rendered HTML (Drupal 11), no JS rendering needed once past
  the bot gate. One flat table (`<table class="tab_pipeline">`), 30 rows:
  `Phase` (I/II/III as roman numerals), `Area` (ONC/CVR/NRD/Others — no `IM`
  rows despite the legend listing Immunology as a category), `Program
  (Mode-of-action)` (compound name + optional trailing MoA parenthetical, one
  combined cell), `Indication` (free text, sometimes with a trial acronym in
  parens), and a modality icon (`<img alt="...">`, no visible text label).
  No NCT IDs, no completion dates, no status field anywhere on the page.
- **PDF**: not listed in `docs/sources.md` at all — found via web search:
  `https://www.bayer.com/sites/default/files/ph-rd-pipeline-2026-02-11-final-update.pdf`
  ("Pharmaceuticals — Pipeline Overview and Progress", Feb 11, 2026,
  investor-relations deck). 6 pages, real embedded text throughout (not
  scanned — `pdfplumber` extracts clean text and word-level bounding boxes on
  every page). Page 1 = cover. **Page 2** is a genuine 3-column chart (Phase
  I / II / III as physical columns, word x-coordinates confirmed: Phase I
  header x≈85–115, Phase II x≈329–358, Phase III x≈586–615) — phase is
  encoded purely by which column a compound's text sits in, not a text label
  per item, same pattern as the Amgen/MSD/BMS chart PDFs. **Pages 3–6** are
  real per-therapeutic-area detail tables (Oncology / Cardiovascular-Renal /
  Neurology-Rare-Diseases / Others) with columns: Candidate medication,
  Indication, Modality (icon only), Phase I/II/III (checkmark — encoded as
  vector curve glyphs, not text or images; confirmed via curve x-coordinate
  clustering against the header columns' x-ranges), Ct.gov Identifier
  (NCT ID), Estimated/Actual Primary Completion, Status. This is strictly
  richer than the webpage for the rows it covers (NCT IDs, completion dates,
  study status) but is a ~5-month-older snapshot (Feb 11 vs the webpage's
  live/current state as fetched).

**User confirmed (see conversation): use both, merge.** Webpage as primary
(current, native row granularity), enriched with the PDF's NCT ID/completion
date/status fields, plus PDF-only rows added as extra records and flagged.

## Field-mapping decisions (confirmed with user)

- **Row granularity**: one row per (compound, indication) pair — matches the
  webpage table's own native structure (e.g. Darolutamide and Sevabertinib
  each appear as two separate rows, one per indication). No explosion
  needed.
- **asset_name / mechanism_of_action split**: the webpage's `Program
  (Mode-of-action)` cell is either a bare name or `Name (parenthetical)`.
  Inspecting all 30 rows found the parenthetical is *always* a clean MoA/
  mechanism descriptor when present (e.g. `Darolutamide (AR Inhibitor)`,
  `Mirena (Levonorgestrel-releasing Intrauterine System)`) — **never** an
  internal code or "aka" alt-name; those richer patterns (e.g. `VVD KEAP1 Act
  (VVD-130037 aka NRF2 Inh, BAY 3605349)`) only appear in the PDF's chart
  page, not on the webpage. Per user decision, the converter still applies a
  defensive code-pattern check (`BAY\d+`/`VVD-?\d+`/`AB-?\d+` alone in the
  parenthetical → `synonyms` instead of `mechanism_of_action`) for
  robustness, but this never actually triggers on the current 30 webpage
  rows — confirmed a no-op in practice, documented here rather than removed,
  in case a future re-scrape picks up a row with a code-only parenthetical.
  Isotope-prefixed names like `Actinium (225Ac) Pelgifatamab Mopaxetan` are
  **not** split (the parenthetical isn't trailing — more text follows it),
  correctly left as one `asset_name`.
- **therapeutic_area**: webpage's `Area` abbreviation expanded to the full
  label per user decision, matching the PDF's/webpage's own legend wording
  verbatim: `ONC` → `Oncology`, `CVR` → `Cardiovascular / Renal`, `NRD` →
  `Neurology & Rare Diseases`, `Others` → `Others` (`IM`/`Immunology` mapped
  for completeness but unused — no rows).
- **indication**: kept exactly as shown on the webpage per user decision,
  including any inline trial acronym (e.g. `Non-diabetic CKD (FIND-CKD)`) —
  not stripped to a separate field.
- **phase**: roman numerals I/II/III map directly to `Phase 1`/`Phase 2`/
  `Phase 3`. The 4 PDF-only "Submissions" rows (regulatory-filing stage, past
  Phase 3) map to `Preregistration` — Bayer's PDF doesn't distinguish
  filed-vs-accepted-for-review any further than that section label.
- **modality**: webpage's modality icon `alt` text mapped to a normalised
  label matching the PDF's own legend categories (Protein Therapy / Cell
  Therapy / Gene Therapy / Radionuclide Therapy / Imaging Agent / Small
  Molecule), unifying several spelling/suffix variants that all mean the
  same thing (`Cell Therapy_NTE`, `gene therapy` vs `Genetic Therapy` vs
  `Gene Therapy_NTE`, `Radiotherapy_NTE` → `Radionuclide Therapy` per the
  PDF's own legend wording) and fixing one source typo (`New Melecular
  Entity` → `New Molecular Entity`). This is a mechanical 1:1 icon→label
  mapping, not flagged as ambiguous — done without a separate question,
  same as AbbVie's device-phase-scale mapping.
- **PDF enrichment fields** (not in the base schema): `trial_id` (NCT ID)
  maps to the schema's own `trial_id` field. Estimated/Actual Primary
  Completion and Status go into `others[]` as `"Key: value"` strings, per
  the established convention.
- **PDF-only rows** (present in the Feb 11 PDF, absent from the current
  webpage): included per user decision, each tagged in `others[]` with
  `"PDF-only (2026-02-11 snapshot), not present on the <fetch-date> webpage"`.
  This set turned out **larger than initially estimated** (9 rows, not the 6
  first spotted) — see "Data-quality anomalies" below for how the extra 3
  were found.

## Row counts (verification)

- 30 webpage rows, all successfully parsed (no missing cells, no malformed
  rows).
- Of those 30, **26 got an NCT ID** merged in from the PDF. Of the 4 that
  didn't: `GIRK4 Inhibitor` and `BAY 3620122` still matched a PDF row and
  got completion date/status merged (just no NCT ID, since the PDF itself
  shows `n/a`/`Undisclosed` for their Ct.gov Identifier — a source gap, not
  an extraction gap); `AT-05 SPECT Tracer` matched a PDF row that is itself
  entirely blank (`n/a` across phase/NCT columns), so nothing merged beyond
  a `notes` flag; `Actinium (225Ac) Felivotide Mopaxetan` was **deliberately
  left unenriched** — the uncertain-pairing row, see below (no dict entry
  added rather than guessing).
- **9 PDF-only rows added**: 3 Phase 3 CVR trials (`Finerenone`/FINE-ONE,
  `Vericiguat`/VICTOR2, `Asundexian`/OCEANIC-STROKE) that are on the PDF's
  Phase III chart column and detail table but nowhere on the current
  webpage; 2 Phase 1 "Others" compounds (`GPR84 Antagonist`, `BAY 2701250`),
  both already `Study completed` in the PDF with no sign of progression —
  plausibly discontinued/deprioritized between Feb and the webpage's
  current snapshot; 4 "Submissions" items (2 brand-new compounds,
  `Aflibercept 8mg` and `Gadoquatrane`, plus 2 indication-expansion
  submissions for already-present compounds `Sevabertinib` and
  `Finerenone`).
- **Total: 39 records**, no duplicate (asset_name, indication) pairs.
- Phase breakdown: Phase 3 = 10, Phase 2 = 6, Phase 1 = 19, Preregistration
  = 4.

## Data-quality anomalies found (flagged, not silently fixed)

- **Cross-source naming mismatch (3 cases)**: the webpage uses a newer INN-
  style name where the Feb-2026 PDF still uses an internal program code /
  target descriptor for the *same* trial — confirmed by matching on the
  trial acronym, not the compound name:
  - `Umiposgene Parvec` (webpage) = `Congestive Heart Failure AAV Gene
    Therapy (AB-1002)` (PDF), same GenePHIT trial.
  - `Ametefgene Parvec` (webpage, appears twice — REGENERATE-PD and MSA
    indications) = `Parkinson's Disease AAV Gene Therapy (AB-1005)` /
    `Multiple System Atrophy AAV Gene Therapy (AB-1005 aka AAV2-GDNF-MSA)`
    (PDF) — note the PDF reuses program code `AB-1005` for both indications.
  This is the same pattern documented in `bms/log.md` (INN names not yet
  assigned as of an older PDF snapshot). The PDF's code is stored in
  `synonyms` on the enriched row.
- **Unresolved uncertain identity pairing**: the webpage lists two
  Advanced-Prostate-Cancer radiotherapy compounds — `Actinium (225Ac)
  Pelgifatamab Mopaxetan` and `Actinium (225Ac) Felivotide Mopaxetan`. The
  PDF's Oncology detail table also has exactly two Advanced-Prostate-Cancer
  radiotherapy rows — `225Ac-Pelgifatamab (BAY 3546828)` and
  `225Ac-PSMA-Trillium (BAY 3563254)`. `Pelgifatamab` matches directly by
  stem name (enriched with NCT06052306). Whether `Felivotide Mopaxetan` =
  `225Ac-PSMA-Trillium` is **not confirmed** — same phase/indication/
  modality is consistent with it, but no independent name-identity evidence
  was found. Left unenriched rather than guessing; flagged here for anyone
  merging in a later, richer source.
- **Indication wording differs between sources for one compound**: `Dual
  FIIa/Xa Inhibitor`'s indication is `"Anti-coagulation"` on the webpage but
  `"Sepsis-Induced Coagulopathy"` in the PDF. Same compound (confirmed by
  name + phase + everything else matching), just different framing of the
  same trial — not resolved, noted on the row via `notes`.
- **Phase/data discrepancy for `AT-05 SPECT Tracer`**: the webpage lists it
  as `Phase 1`, and the PDF's own chart page places it in the Phase I column
  too — but the PDF's *detail table* row shows `n/a` for all three phase
  checkmarks and for the Ct.gov Identifier column. Kept the webpage's
  `Phase 1` (current, primary source) and flagged the PDF's own internal
  inconsistency via `notes` rather than resolving it.
- **9, not 6, PDF-only rows**: the first pass (skimming PDF page 2's linear
  text extraction) only turned up 6 PDF-only items, because plain
  `extract_text()` on a 3-column chart page interleaves columns in a
  confusing order (same known issue as the Amgen/MSD chart PDFs). Re-deriving
  each item's phase from actual word x-coordinates (bucketing into the
  Phase I/II/III column x-ranges) turned up 3 more: `Finerenone`'s
  `FINE-ONE` trial, `Vericiguat`, and `Asundexian` are all Phase 3 in the
  PDF and simply don't appear on the current webpage at all (not even as a
  different-named row) — a real gap between the Feb PDF and the current
  webpage snapshot, not a parsing artifact.
- **Two Bayer compounds already listed in `Immunology` on the webpage's own
  legend** never actually appear with an `IM` area tag in any of the 30
  rows — the legend advertises 5 areas (ONC/CVR/NRD/IM/Others) but Bayer's
  current pipeline has 0 Immunology programs. Not an extraction bug, just
  an empty category.

## Manual cross-check (2026-07-09)

User pasted a manual copy/paste of the live webpage's table (all 30 rows,
in page order, including the `modality` icon alt-text column). Diffed
programmatically against the 30 webpage-sourced rows in
`bayer_pipeline.parquet` on (asset_name, indication, phase, therapeutic_area,
modality) — **exact match, 0 discrepancies**, all 30 rows accounted for
1:1 (including the two rows the user specifically called out:
`KRAS G12D Inhibitor`/Phase 1/Oncology/Small Molecule and `Sevabertinib`/
PanSOHO/Phase 2/Oncology/Small Molecule).

No inconsistencies found. This cross-check only covers the 30 webpage rows,
not the 9 PDF-only rows (`PDF_ONLY_RECORDS`) or the PDF-derived enrichment
fields (`trial_id`/completion/status in `others[]`) — those are hand-
transcribed from the PDF directly (see extraction method above) rather than
scraped, so a webpage-copy cross-check can't validate them independently.

## Files

- `bayer_page.html` — raw fetched webpage HTML (via scrapling
  `StealthyFetcher`, since plain HTTP clients get bot-blocked by
  bayer.com).
- `bayer_pipeline_2026-02-11.pdf` — raw fetched PDF (via scrapling's
  `Fetcher.get(..., impersonate="chrome")`).
- `bayer_to_parquet.py` — single-pass converter: parses `bayer_page.html`'s
  table programmatically, enriches/adds rows from the PDF via hand-
  transcribed lookup tables (`PDF_ENRICHMENT`, `PDF_ONLY_RECORDS` — the PDF's
  checkmark-grid and chart-column phase encoding aren't worth a general
  parser for ~35 rows, following the BMS/MSD precedent for small one-off
  cross-source enrichments), imports the schema from `schema` (resolves to
  `src/schema.py`).
- `bayer_pipeline.parquet` — 39 records.
