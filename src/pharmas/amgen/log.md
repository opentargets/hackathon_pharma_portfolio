# Amgen — extraction log

Tier 2 in `docs/sources.md` ("Interactive JS-rendered widget — static HTML
has no data ... Separate quarterly PDF ... likely vector-based, not a
literal table."). Tracked in GitHub issue
[#18](https://github.com/opentargets/hackathon_pharma_portfolio/issues/18).

## Source discovery

Checked both possible source types before starting, per
`instruction_for_agent.md` — and found a third option neither note
anticipated:

- **Webpage** (`https://www.amgenpipeline.com/`): confirmed static HTML has
  no data (data loaded client-side). But the page's own JS
  (`pipeline-custom.js`) loads it via a plain, **unauthenticated GET** to
  `https://www.amgenpipeline.com/pipeline/molecule/getjsondata` — the
  anti-forgery-token call is commented out in the source JS. `curl`ing that
  endpoint directly (no cookies, no browser, no Playwright) returns the full
  dataset: 30 molecules, 42 molecule×indication rows (7 molecules have
  multiple indication/phase entries). Each row carries `MoleculeName`,
  `MoleculeCode`, `Description`, `AdditionalInformation`,
  `TherapeuticAreas` (label + `TA#` id), `Phase` (explicit numeric 1/2/3 +
  `PH#` id), `Indications` (array of label + `IN#` id), `Modality`.
- **Downloadable file**: a quarterly "Download Pipeline Chart" PDF exists
  (`.../PDF/amgen-pipeline-chart.pdf`). Downloaded and parsed with
  `pdfplumber`: same 30 molecules, same indication breakdown as the JSON
  (verified by diffing molecule name lists — exact match) and the same
  Description/AdditionalInformation/Modality/TherapeuticArea/Indication
  text. **The PHASE column is graphical** (bar/chart position, not text) —
  confirmed via `extract_tables()`, the Phase cell comes back empty for
  every row. Recovering phase from the PDF would need coordinate/shading
  analysis (same risk class as MSD's/BMS's chart-style PDFs) for no benefit,
  since the JSON already has explicit numeric phase.

Confirmed with the user: **use the JSON endpoint only** — it's a strict
superset of the PDF's content plus machine-readable phase, no merge needed.

## Row counts (verification)

- 42 molecule×indication rows, 30 unique molecules.
- No duplicate (molecule_name, first indication, phase) rows.
- Phase breakdown: Phase 3 = 27, Phase 2 = 9, Phase 1 = 6.
- Therapeutic area breakdown: Hematology / Oncology = 9, Inflammation = 8,
  Cardiometabolic = 7, Rare Disease = 6, Bone = 1, Diabetes = 1,
  Nephrology = 1, Neuroscience = 1 (counts are per-row, not per-molecule,
  since a molecule can appear under different TAs for different
  indications, e.g. `blinatumomab`/BLINCYTO spans Hematology/Oncology and
  Inflammation).

## Field-mapping decisions (confirmed with user)

- **Row granularity**: one row per molecule × indication-page — matches the
  source's own native structure (`Pages[]` per molecule), no explosion
  needed.
- **asset_name / synonyms — four distinct naming patterns found**, per user
  decision (generic/INN name or compound code as `asset_name`, brand name
  and any old code/nickname as `synonyms` — following the AstraZeneca
  precedent):
  1. Brand name + generic in the `MoleculeCode` field, e.g. `Aimovig®` /
     `(erenumab-aooe)` → `asset_name="erenumab-aooe"`,
     `synonyms=["Aimovig"]`.
  2. Brand name + generic embedded directly in `MoleculeName`
     (`MoleculeCode` empty), e.g. `LUMAKRAS®(sotorasib)` →
     `asset_name="sotorasib"`, `synonyms=["LUMAKRAS"]`. Disambiguated from
     pattern 4 below by checking for a ®/™ symbol on the outer name (after
     HTML-entity unescaping — `&reg;` only becomes a matchable `®`
     character post-unescape, which caught a bug, see below).
  3. Investigational biosimilar codes with no generic name assigned yet,
     `MoleculeCode` instead describes the reference product, e.g. `ABP 206`
     / `(Investigational biosimilar to OPDIVO® (nivolumab))` →
     `asset_name="ABP 206"`, no synonyms, and
     `others=["Biosimilar of: nivolumab (OPDIVO)"]`.
  4. No brand at all — either a bare generic/INN name or a bare internal
     code, optionally with an old code/nickname noted "formerly X", e.g.
     `Maridebart Cafraglutide (MariTide, formerly AMG 133)` →
     `asset_name="maridebart cafraglutide"`,
     `synonyms=["MariTide", "AMG 133"]`; `AMG 732 (formerly HZN-280)` →
     `asset_name="AMG 732"`, `synonyms=["HZN-280"]`; `Daxdilimab` →
     `asset_name="daxdilimab"`, no synonyms.
  - **Casing normalization**: the source displays every non-branded
    molecule name in ALL CAPS in the `MoleculeName` heading (e.g.
    `DAZODALIBEP`, `MARIDEBART CAFRAGLUTIDE`), but each one's own
    `Description` text refers to it in standard INN lower-case form (e.g.
    "Dazodalibep is a...", "Maridebart cafraglutide is a..."), matching the
    lower-case INN style already used natively in the `MoleculeCode` field
    for pattern-1 molecules (`erenumab-aooe`, `sotorasib`, etc.). Per this
    consistency, any generic/INN-style prefix (no digit) is lower-cased;
    internal codes (`AMG 732`, `ABP 206` — contain a digit) are left as-is.
- **mechanism_of_action**: extracted from `Description` with 3 patterns,
  per user decision:
  1. Main: `"<Name> is a/an <MoA phrase>. It is being investigated..."` —
     covers the majority of rows.
  2. No-period variant: `"<Name> is a/an <MoA phrase> being investigated..."`
     — covers 4 early-phase codes (AMG 410, AMG 436, AMG 513, AMG 691) whose
     description sentence has no period before "being investigated".
  3. Biosimilar variant: `"...is an investigational biosimilar to X
     (generic), which is a/an <MoA phrase>..."` — the `<MoA phrase>` after
     "which is" is used as `mechanism_of_action`; the biosimilar target
     itself goes to `others` (see pattern 3 above).
  - `AMG 513`'s description ("AMG 513 is a molecule being investigated for
    the treatment of obesity.") has no disclosed modality/MoA beyond
    "molecule" — `mechanism_of_action="molecule"`, `modality=None`, a
    genuine source gap (not a mapping choice).
- **therapeutic_area**: kept verbatim from the source's `TherapeuticAreas`
  label (`Neuroscience`, `Hematology / Oncology`, `Bone`, `Nephrology`,
  `Cardiometabolic`, `Rare Disease`, `Inflammation`, `Diabetes`) — already
  consistently cased, no ambiguity.
- **indication (multi-indication rows)**: 7 molecule-rows list 2-3
  `Indications` per page, but only the first is a specific disease — the
  rest are broader filter tags that duplicate/overlap `therapeutic_area`
  (e.g. TEZSPIRE's COPD row also tags "Respiratory Disease" and
  "Inflammatory Disease"). Confirmed by cross-checking each row's own
  `Description` text, which only ever names the first indication. Per user
  decision: `indication` = first (specific) tag; remaining tags go into
  `others[]` as `"Indication tag: <label>"`.
- **phase**: `Phase.HtmlString` "1"/"2"/"3" map directly to `Phase 1/2/3`.
  No ambiguous phase terms in this source (no "Registration"/"Filed" seen).
- **modality**: mapped directly from `Modality`, HTML tags/entities
  stripped (e.g. `BiTE<sup>&reg;</sup> Molecule` → `BiTE® Molecule`). Empty
  for `AMG 513` (source gap, see above).
- **notes**: `AdditionalInformation` free text (mostly collaboration/partner
  disclosures, e.g. "Aimovig is developed in collaboration with Novartis.")
  mapped as-is when present, else `null`.
- **trial_id**: not present anywhere in the source (no NCT numbers) — left
  `null` for all 42 rows.
- **source_url / extraction_date**: `source_url` set to the human-facing
  pipeline homepage (`https://www.amgenpipeline.com/`), not the raw JSON
  endpoint, for consistency with how other companies' `source_url`s point at
  the page a person would visit — the endpoint itself is documented in
  `scrape_pipeline.py`. `extraction_date` = 2026-07-09 (fetch date). Note:
  the PDF's own disclaimer states data is "as of April 30, 2026" — this is
  the site's own snapshot date, not the fetch date, and isn't carried into
  the per-row schema (it applies to the whole dataset, not any one row).

## Data-quality anomalies found (flagged, not silently fixed)

- **Trademark-symbol detection bug caught before finalizing**: the first
  converter pass checked for `®`/`™` against the *raw, still-HTML-escaped*
  `MoleculeName` string (which contains the literal text `&reg;`, not the
  `®` character), so pattern-2 molecules with `&reg;` in the raw JSON
  (`IMDELLTRA&reg;(tarlatamab-dlle)`, `TEPEZZA&reg;(teprotumumab-trbw)`,
  `TEZSPIRE&reg; (tezepelumab-ekko)`) fell through to the "no brand"
  pattern-4 branch instead, producing `asset_name="imdelltra®"` (wrong —
  should be `"tarlatamab-dlle"`, brand as synonym). Caught during my own
  spot-check of the converter output (before reporting the extraction as
  done), not by the user's manual cross-check. Fixed by checking the
  trademark symbol against the already-HTML-unescaped name string instead
  of the raw one.
- **Lower-casing gap caught in the same pass**: the "bare code or INN name,
  nothing else on the page" branch (`Dazodalibep`, `Daxdilimab`,
  `Inebilizumab`) initially skipped the lower-case-if-no-digit
  normalization applied elsewhere, leaving `asset_name="DAZODALIBEP"` etc.
  in all-caps, inconsistent with pattern-1/2/4 molecules of the same kind.
  Fixed by applying the same digit-check rule uniformly across all
  no-parenthetical and de-parenthesized branches.
- **`AMG 513` has no modality disclosed** beyond the generic word
  "molecule" in its description — a genuine source gap (see
  mechanism_of_action above), not an extraction bug.
- No trial IDs (NCT numbers) anywhere in the source — a genuine source gap,
  consistent with this being marketing/investor-facing pipeline content
  rather than a clinical-trials registry export.

## Manual cross-check (2026-07-09)

User provided a full copy/paste of the live webpage's rendered table (all
42 rows, in page order) plus the full "DESCRIPTION" / "ADDITIONAL CLINICAL
STUDIES" / "ADDITIONAL INFORMATION" text for 3 specific rows (BLINCYTO ×2,
Nplate).

1. **Table diff**: parsed the pasted text programmatically and diffed
   against `raw_pipeline.json` on (therapeutic_area, indication, modality,
   phase) per row, positionally — **exact match, 0 discrepancies** across
   all 42 rows.
2. **Description text diff**: the 3 pasted DESCRIPTION blocks matched
   `raw_pipeline.json`'s `description` field verbatim. But comparing
   BLINCYTO's pasted block surfaced a real gap: the page renders a distinct
   **"ADDITIONAL CLINICAL STUDIES"** heading for BLINCYTO's ALL row (text:
   "Blinatumomab is also in Phase 2 development being investigated for
   subcutaneous administration..."), but in the underlying JSON this text is
   **not a separate field** — it's concatenated straight into `Description`
   after the literal heading string "ADDITIONAL CLINICAL STUDIES", with no
   structural delimiter. The converter's first pass only ever extracted the
   leading "is a/an X." clause for `mechanism_of_action` and used the
   separate (and, for this row, empty) `AdditionalInformation` field for
   `notes` — so this entire clause was silently dropped from the schema
   output, not stored anywhere.
   - Checked how widespread this is: 4/30 molecules have this embedded
     heading (BLINCYTO, IMDELLTRA, LUMAKRAS, XALURITAMIG), all on their
     first/lead indication row.
   - **Fixed**: `split_description()` now splits `Description` on the
     "ADDITIONAL CLINICAL STUDIES" marker when present; the clause after it
     is prefixed `"Additional clinical studies: "` and appended to `notes`
     (alongside the separate `AdditionalInformation` text, e.g.
     XALURITAMIG's row now has both the clinical-studies clause and the
     "XmAb is a registered trademark of Xencor, Inc." disclosure in
     `notes`). `mechanism_of_action` extraction now runs against the
     pre-split main clause only (no behavior change there — the regex
     already stopped at the first sentence).
   - Re-ran the full 42-row table diff after the fix: still 0 discrepancies.

## Files

- `amgen_raw.json` — raw fetched JSON (full endpoint response, provenance).
- `scrape_pipeline.py` — pass 1: fetches the `getjsondata` endpoint directly
  (fully static GET, no browser needed), flattens each molecule's `Pages[]`
  into one row per molecule×indication-page -> `raw_pipeline.json`.
- `raw_pipeline.json` — raw fetch output, 42 unmapped rows.
- `amgen_to_parquet.py` — pass 2: maps `raw_pipeline.json` onto
  `PipelineRecord` (imported from `schema` per the shared-schema convention)
  -> `amgen_pipeline.parquet`.
- `amgen_pipeline.parquet` — 42 records.
