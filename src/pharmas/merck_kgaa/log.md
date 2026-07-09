# Merck KGaA — extraction log

Tier 3 in `docs/sources.md` ("Interactive filterable tracker"). Tracked in
GitHub issue
[#33](https://github.com/opentargets/hackathon_pharma_portfolio/issues/33).

## Source discovery

Checked both a downloadable file and the webpage itself before trusting the
Tier 3 label, per `instruction_for_agent.md`.

- **Webpage** (`https://www.merckgroup.com/en/research/healthcare-pipeline.html`):
  plain `curl` (browser UA, `--http1.1`) returns HTTP 200 — no WAF/bot-block
  at all, unlike Bayer/Boehringer. The page itself has no pipeline data in
  static HTML/data-attrs (the widget's placeholders like `item.thumbnail`
  are unfilled template tokens). But its own inline script
  (`/content/dam/scripts/group/en/pipeline/script.js`) reveals the widget
  just appends a second `<script>` tag pointing at a plain JS file
  (`docPath` + `jsonDocument`, where `docPath` comes from a hidden
  `<div id="contentdiv"><p class="filePath">` on the page) — no click-loop,
  no Playwright needed, just one more static fetch:
  `https://www.merckgroup.com/content/dam/scripts/group/en/pipeline/data.js`.
  That file is `pipelineData = [...]`, near-valid JSON (strip the
  `pipelineData = ` prefix, drop the trailing `;`), 10 rows across 3
  therapeutic areas (Oncology 6, Neurology & Immunology 3, Global Health 1).
  Fields: `type` (area), `title1` (compound + trailing MoA parenthetical),
  `title2` (indication, with embedded footnote `<sup>` tags), `phase`
  (1–4, numeric — "4" labelled "Registration" in the widget's own filter
  legend), `phasetext` (sub-phase, e.g. "1b", only on one row), `year`
  (present on 6/10 rows, meaning not disclosed by the source), `asset`
  (internal/external origin), `compound` (chemical/biological/antibody),
  `entity` (readable class label: "New Chemical Entity" / "New Biological
  Entity" / "Antibody Drug Conjugate"), `description` (MoA prose), up to 6
  clinical-trial links (mostly Merck-internal trial IDs on
  clinicaltrials.merckgroup.com/emdgroup.com, not standard NCT numbers).
- **PDF** (`Healthcare-Pipeline-EN.pdf`, dated May 21, 2026): linked
  directly from the webpage's own HTML
  (`/content/dam/web/corporate/non-images/business-specifics/healthcare/global/Healthcare-Pipeline-EN.pdf`),
  also fetches fine via plain curl, no bot-block. Same 10 compound/
  indication pairs as the JSON — phase is encoded as chart-column position
  (Phase 1/2/3/Registration headers), not a text field. Adds footnote prose
  per asset: license agreements (pimicotinib/Abbisko), regulatory filing
  status (pimicotinib's FDA NDA acceptance), patient-subgroup detail
  (enpatoran's lupus subtype, M3554's tumor types), combination-therapy
  notes (cabamiquine + pyronaridine) — none of which is in the JSON's
  `description` field.
- **Footnote numbering mismatch (confirmed)**: the JSON's own embedded
  `<sup>` footnote numbers (inside `title1`/`title2`) don't match the PDF's
  footnote numbering for the same asset — e.g. cladribine is `<sup>5</sup>`
  in the JSON but is footnote "3" in the PDF; precemtabart's colorectal
  row is `<sup>3</sup>` in the JSON but footnote "5" in the PDF. The two
  renderings of the same underlying CMS content are out of sync on
  numbering. Footnotes were therefore matched to JSON rows by
  **asset name + indication**, not by number.

**User confirmed: use both, merged.** JSON as the structured row source;
PDF footnote prose appended to `notes` via a hand-transcribed
(asset_name, indication) lookup, same precedent as Bayer's
`PDF_ENRICHMENT` dict.

## Field-mapping decisions (confirmed with user)

- **`asset_name` / `mechanism_of_action` split**: `title1` is always
  `"Name (parenthetical)"` or a bare name. Split into `asset_name` (bare
  compound) + `mechanism_of_action` (parenthetical), kept verbatim even
  where the parenthetical reads as MoA+modality combined (e.g.
  "anti-CEACAM5 Antibody drug conjugate") — per user decision, not trimmed
  down to a pure-MoA fragment.
- **`phase`**: `1`/`2`/`3` map directly to `Phase 1`/`Phase 2`/`Phase 3`.
  `4` (widget's own "Registration" filter label) maps to
  `Phase.PREREGISTRATION`, per user decision — matches Bayer's convention
  for regulatory-filing-stage items without a distinct
  filed-vs-accepted-for-review split.
- **Sub-phase `phasetext="1b"`** (only on the precemtabart/pan-tumor row):
  mapped to `Phase.PHASE_1` (no Phase 1b value in the schema enum); the
  "1b" detail is preserved in `others` as `"Sub-phase: 1b (...)"`, per user
  decision — not dropped.
- **`entity` → `modality`**: mapped directly, 1:1, no normalization table
  needed (only 3 distinct values across all 10 rows: New Chemical Entity,
  New Biological Entity, Antibody Drug Conjugate).
- **`trial_id`**: populated only where a genuine NCT number is present —
  1 row (M7437), whose link URL text itself ends in `-NCT07360314`. All
  other rows' Merck-internal trial IDs/URLs (clinicaltrials.merckgroup.com
  / clinicaltrials.emdgroup.com, IDs like `MS202329_0001`) go to `others`
  as `"Clinical trial: <link text> - <url>"` strings instead, per user
  decision (trial_id reserved for real NCT numbers).
- **PDF footnote prose**: matched to JSON rows by (asset_name, indication)
  and appended to `notes` (not `others`), per user decision — `others` kept
  for the mechanical source-field carry-overs (origin, year, sub-phase,
  trial links) while `notes` holds this richer prose annotation.
- **`asset` (internal/external origin) and `year`**: both kept in `others`
  per row when present (`"Origin: Internally/Externally Derived"`,
  `"Year: <value>"`), per user decision — no interpretation asserted about
  what `year` means (not confirmed by the source itself whether it's
  licensing year, first-in-human year, or something else).
- **`therapeutic_area`**: kept verbatim from the JSON's `type` field
  ("Oncology", "Neurology & Immunology", "Global Health") — not normalized
  to a shared vocabulary yet, per the deferred-vocabulary convention.
- **`indication`**: `title2` with embedded `<sup>...</sup>` footnote-marker
  tags stripped (they're just superscript reference numbers, not part of
  the indication text).

## Row counts (verification)

- 10 rows total: Oncology 6, Neurology & Immunology 3, Global Health 1 —
  matches the JSON's own area grouping exactly.
- Phase breakdown: Phase 1 = 5, Phase 2 = 1, Phase 3 = 3, Preregistration
  (source "4"/Registration) = 1 (pimicotinib).
- No duplicate (asset_name, indication) pairs — precemtabart tocentecan
  appears twice (Colorectal Cancer 3L / Phase 3, and Pan tumor / Phase 1)
  as two genuinely distinct indication rows, matching the source's own
  structure (same pattern as Bayer's Darolutamide/Sevabertinib repeats).
- All 10 rows present in both the JSON and the PDF (same compound +
  indication set, cross-checked by eye) — no PDF-only or JSON-only rows,
  unlike Bayer's asymmetric merge.

## Data-quality anomalies found (flagged, not silently fixed)

- **Footnote superscript numbering mismatch between JSON and PDF**
  (described above under Source discovery) — not a bug in either source
  individually, just two out-of-sync renderings of the same CMS content.
  Resolved by matching footnotes on asset identity instead of number.
- **`year` field's meaning is undisclosed** by the source (present on 6/10
  rows, absent on the other 4 with no visible pattern distinguishing them)
  — carried through to `others` verbatim per user decision, not
  interpreted.

## Manual cross-check (2026-07-09)

User pasted a manual copy/paste of the live webpage's Oncology / Neurology
& Immunology / Global Health sections (all 10 rows, in page order,
including embedded footnote superscripts), plus two spot-checked rows with
their `Phase`/`Entity:` fields.

- All 10 asset/indication pairs match `merck_kgaa_pipeline.parquet`
  exactly, same order, same footnote-marker positions (`1,2` / `3` / `1b` /
  `4` / none / none / `5` / `6` / `7` / `8`).
- `precemtabart tocentecan` / "Colorectal Cancer 3L": pasted `Phase 3` /
  `Entity: Antibody Drug Conjugate` — matches parquet (`Phase 3` /
  `Antibody Drug Conjugate`).
- `M5542` / "T cell-mediated autoimmune diseases": pasted `Phase 1` /
  `Entity: New Biological Entity` — matches parquet (`Phase 1` /
  `New Biological Entity`).

**No inconsistencies found.**

## Files

- `merck_kgaa_data.js` — raw fetched widget data file (`pipelineData = [...]`,
  fetched via plain curl with a browser UA).
- `merck_kgaa_pipeline_2026-05-21.pdf` — raw fetched PDF (also plain curl,
  no bot-block).
- `merck_kgaa_to_parquet.py` — single-pass converter: parses
  `merck_kgaa_data.js` programmatically, enriches with PDF footnote prose
  via a hand-transcribed `(asset_name, indication)` lookup (`PDF_FOOTNOTES`),
  imports the schema from `schema` (resolves to `src/schema.py`).
- `merck_kgaa_pipeline.parquet` — 10 records.
