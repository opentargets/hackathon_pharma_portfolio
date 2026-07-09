# Bristol Myers Squibb (BMS) — extraction log

Tier 2 in `docs/sources.md` ("Live HTML pipeline page. Compound + indication
pairs per area, not a strict table. Excludes collaborations."). Tracked in
GitHub issue [#17](https://github.com/opentargets/hackathon_pharma_portfolio/issues/17).

## Source discovery

Checked both possible source types before starting, per
`instruction_for_agent.md`:

- **Downloadable file**: none exists. `curl`ing the pipeline page for PDF
  links only turns up prescribing-information PDFs for already-approved
  products (`packageinserts.bms.com/pi/pi_*.pdf` — Cobenfy, Krazati, Opdivo,
  Opdivo Qvantig, Reblozyl, Sotyktu, Yervoy) and an unrelated corporate policy
  PDF. No pipeline chart/table PDF/CSV.
- **Webpage**: `curl`ing
  `https://www.bms.com/research-and-development/pipeline.html` (plain,
  no browser) returns HTTP 200 with the full dataset already embedded —
  fully static, no JS rendering needed despite the page being an interactive
  filterable widget in the browser. The data lives in a hidden
  `<div id="pipeline-data">` as an HTML-entity-escaped JSON blob containing:
  - `listings`: 91 compound×indication rows, each with `compoundname`,
    `category` (therapeutic area slug), `subcategory` (indication slug),
    `phaseTag`, `researcharea` (free text, ~40% populated), `nmedatastatus`
    (NME Lead / NME / non-NME), `registrationstatus` (region detail, only
    populated on the 3 Registration-phase rows).
  - `therapeuticarea`: a lookup table resolving `category`/`subcategory`
    slugs to their human-readable labels (must be joined against `listings`
    to get real indication text).
  - `phase`: lookup for `phaseTag` -> phase name.

  Confirmed with the user to use this as the sole source (no file exists to
  compare against or merge with).

## Row counts (verification)

- 91 listing rows, 50 unique compounds (many compounds appear across
  multiple indications, e.g. `pumitamig` has 9 rows).
- Phase breakdown: Phase 3 = 35, Phase 1 = 34, Phase 2 = 19, Preregistration
  (source: "Registration") = 3.
- Therapeutic area breakdown: Oncology = 40, Hematology = 19, Neuroscience =
  16, Immunology = 13, Cardiovascular = 3.
- No duplicate (asset_name, indication, therapeutic_area, phase) rows.

## Field-mapping decisions (confirmed with user)

- **Row granularity**: one row per (compound, indication) pair — matches the
  webpage's own native structure, no explosion needed.
- **asset_name / synonyms — three distinct name patterns found and
  disambiguated**:
  1. Plain name, no parenthetical (e.g. `milvexian`, `BMS-986460`) — used
     as-is.
  2. `BRAND® (generic)` / `BRAND™ (generic)` (e.g. `REBLOZYL® (luspatercept-
     aamt)`, `OPDIVO® (nivolumab)`) — disambiguated by the trademark symbol:
     `asset_name` = generic name, brand (symbol stripped) -> `synonyms`.
  3. `code-name (parenthetical)` with **no** trademark symbol (e.g. `CD19 TCE
     (BMS-986528)`, `imzokitug (Anti-CCR8)`) — initially mis-handled by
     applying pattern 2's brand/generic split uniformly (backwards result:
     asset_name became the BMS internal number, e.g. `BMS-986528`, with the
     real name `CD19 TCE` demoted to a synonym). Caught before finalizing,
     not after — see below. Fixed per user decision: outer name is always
     the real identifier (kept as `asset_name`); the parenthetical is either
     a real BMS internal code (matches `BMS-\d+`, e.g. `BMS-986528`,
     `BMS-986482`) -> `synonyms`, or a target/MoA descriptor (e.g.
     `Anti-CCR8`, `FAAH/MAGL Dual Inhibitor`, `Anti-MTBR Tau`) ->
     `mechanism_of_action` (the only source of MoA data found — see below).
  - **Combos**: 2-drug rows joined with "+" in the source (e.g. `atigotatug +
    nivolumab`, `OPDIVO QVANTIG™ (nivolumab and hyaluronidase-nvhy) + YERVOY®
    (ipilimumab)`) are kept as a single row with `asset_name` = each
    constituent split independently per the rules above, then rejoined with
    `" + "` (e.g. `"nivolumab and hyaluronidase-nvhy + ipilimumab"`),
    synonyms/MoA hints concatenated across constituents.
- **mechanism_of_action**: not disclosed as a dedicated field anywhere in
  the source for the vast majority of compounds. The only MoA-like text
  available is the target/mechanism descriptor riding along in a handful of
  parenthetical compound names (5 compounds: `imzokitug`, `irafamdastat`,
  `moponetug`, plus the two `... Pan-Degrader`/`... TCE` code-name rows) —
  used per the decision above. All other 45 compounds have `null`
  mechanism_of_action; this is a genuine source gap, not a mapping choice.
- **therapeutic_area**: kept verbatim from the source's `category` label
  (`Cardiovascular`, `Hematology`, `Immunology`, `Neuroscience`, `Oncology`)
  — already title-cased, no ambiguity.
- **indication**: resolved from the `subcategory` slug via the
  `therapeuticarea` lookup table. 7 labels carry a trailing footnote
  asterisk (e.g. `"Secondary Stroke Prevention*"`, `"1L Non-Small Cell Lung
  Cancer*"`) whose meaning is unknown — the explanatory footnote is
  presumably rendered client-side by the page's JS widget and is absent from
  the static HTML this extraction reads. Per user decision, the asterisk is
  stripped (treated as a cosmetic marker, not part of the indication text).
- **phase**: `phase-1`/`phase-2`/`phase-3` map directly to `Phase 1/2/3`.
  `Registration` (3 rows) maps to `Preregistration` per user decision — BMS's
  page doesn't distinguish submitted-vs-accepted-for-review, all 3
  Registration rows carry a `registrationstatus` region tag instead
  (`Registration (US)`, `Registration (EU)`, `Registration (EU, JP)`).
- **trial_id**: not present anywhere in the source (no NCT numbers) — left
  `null` for all 91 rows.
- **Extra source fields kept, not dropped**: `nmedatastatus` (NME Lead / NME
  / non-NME — BMS's own internal designation of how far along/prioritized a
  compound is), `researcharea` (a broader disease grouping than
  `indication`, e.g. `"Lung Cancer"` vs. the specific `"1L Non-Small Cell
  Lung Cancer PD-L1≥50%"` indication), and `registrationstatus` (region
  detail on the 3 Registration rows) — all go into `others[]` as
  `"Key: value"` strings, per user decision.

## Data-quality anomalies found (flagged, not silently fixed)

- **Non-branded parenthetical compound names initially mis-split** — see
  above under asset_name/synonyms. Caught during my own spot-check of the
  converter output (before reporting the extraction as done), not by the
  user's manual cross-check. Fixed by distinguishing the two parenthetical
  patterns on presence of a trademark symbol, confirmed with the user.
- **Trailing footnote asterisk on 7 indication labels** — meaning unresolved
  (footnote text not present in the static HTML fetched; likely rendered
  client-side by JS). Stripped per user decision; flagged here in case a
  future re-extraction with a browser-rendered fetch turns up what it means.
- No mechanism_of_action for 45/50 compounds — a genuine source gap (BMS's
  pipeline page doesn't disclose MoA text the way MSD's or Roche's do), not
  an extraction bug.
- No collaboration/partnered compounds appear at all (per the sources.md
  note) — could not verify this is deliberate exclusion vs. BMS simply having
  none active; not investigated further as it's a known, pre-flagged
  limitation of this source.

## Manual cross-check (2026-07-09)

User provided two independent checks:

1. **Full manual copy/paste of the live webpage's rendered table** (all 91
   rows, in page order). Parsed programmatically and diffed against
   `raw_pipeline.json` on (compound name, category, indication, phase) —
   **exact match, 0 discrepancies** across all 91 rows.
2. **BMS's 2025 annual-report Development Portfolio PDF**
   (`annual-report.bms.com/assets/bms-ar/documents/2025/2025-bms-development-portfolio.pdf`,
   snapshot dated **February 5, 2026** — ~12 weeks before the webpage's own
   "as of April 30, 2026" snapshot) with two specific rows flagged for phase
   verification: `pumitamig` / "1L Extensive-Stage Small Cell Lung Cancer*"
   and `OPDIVO® (nivolumab)` / "Adjuvant Hepatocellular Carcinoma".
   - This PDF is a chart-style, multi-column-per-phase layout like the
     already-known MSD/Amgen "chart PDF" difficulty — `pdfplumber`'s
     page-level `extract_text()` scrambles reading order across columns
     (confirmed: several compound names that ARE in the PDF, e.g. "Dual
     Targeting BCMAxGPRC5D CAR T", don't show up in a naive `extract_text()`
     substring search but do appear correctly when reading `extract_words()`
     binned by their x-coordinate into the 4 phase columns).
   - Using coordinate-based column extraction: both flagged rows land in the
     PDF's **Phase III** column (`pumitamig✦ – ES-SCLC#` and `OPDIVO✦ –
     Adjuvant HCC` both under the Phase III "Additional Indications"
     sub-list) — **matches** this extraction's `Phase 3` mapping for both.
     No discrepancy.
   - Broader compound-coverage check: 45/50 unique compounds confirmed
     present in the PDF once matched by name properly. Of the initial 5
     "missing", 4 turned out to be present under an **older code/target-
     descriptor name** the PDF still uses (`BMS-986482`, `Anti-CCR8`,
     `FAAH/MAGL Dual Inhibitor`, `Anti-MTBR Tau`) — the webpage's newer
     INN-style names (`IKZF Pan-Degrader`, `imzokitug`, `irafamdastat`,
     `moponetug`) simply hadn't been assigned yet as of the PDF's February
     cutoff. Not an extraction error.
   - **1 compound genuinely absent from the PDF**: `CD19 TCE (BMS-986528)`
     (Immunology, Phase 1, Autoimmune Diseases) — not found anywhere in the
     PDF text under either name or code, and not listed among the PDF's own
     partnership-exclusion footnote either. Most likely a pipeline addition
     made between the PDF's Feb 5, 2026 cutoff and the webpage's Apr 30,
     2026 snapshot (a ~12-week gap is plenty for a new Phase 1 entrant).
     Flagged here as a plausible-but-unconfirmed timing explanation, not
     verified against a third source.

**Conclusion**: no inconsistencies found between this extraction and either
cross-check source. The one PDF/webpage compound-count difference (49 vs 50)
is attributable to the ~12-week gap between snapshot dates, not a scraping or
mapping bug.

## Files

- `bms_pipeline_page.html` — raw fetched HTML (provenance).
- `scrape_pipeline.py` — pass 1: fetches the pipeline page (fully static, no
  browser needed), extracts and resolves the embedded `pipeline-data` JSON
  blob into 91 unmapped rows -> `raw_pipeline.json`.
- `raw_pipeline.json` — raw scrape output.
- `bms_to_parquet.py` — pass 2: maps `raw_pipeline.json` onto
  `PipelineRecord` (imported from `schema` per the shared-schema convention)
  -> `bms_pipeline.parquet`.
- `bms_pipeline.parquet` — 91 records.
