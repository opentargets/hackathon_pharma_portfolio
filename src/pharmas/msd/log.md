# Merck & Co. (MSD) — extraction log

Tier 2 in `docs/sources.md` (PDF available, flagged "chart", Phase 1 not
shown). Tracked in GitHub issue [#6](https://github.com/opentargets/hackathon_pharma_portfolio/issues/6).

## Source discovery

Started from the PDF listed in `docs/sources.md`
(`https://www.msd.com/wp-content/uploads/sites/9/2026/05/Public-Pipeline-2Q2026-MSD.pdf`,
linked from the pipeline page). Confirmed it's a genuine vector "chart", not a
flat table: naive text extraction (`pypdf`) returns words in scrambled
reading order because the layout is a grid of boxes read top-to-bottom
column-by-column rather than row-by-row. `pdfplumber` word coordinates
confirmed the real structure: each page has up to 6 columns; within a column,
compound boxes stack vertically (therapeutic area line, indication lines,
optional generic name, bold MK-/V-code, optional footnote digit).

Before committing to a full positional PDF parse (comparable effort to the
Amgen/BMS chart PDFs still `TODO`), the user pointed out the live pipeline
page (`https://www.msd.com/research/product-pipeline/`) has substantially
richer per-compound data (mechanism of action, NCT trial IDs per indication)
than the PDF chart, and asked to scrape it and cross-check phases against the
PDF.

**`curl`-first check paid off**: the page is fully static — no JS
rendering/API call needed. `curl`ing it returns the complete pipeline table
already in the HTML as `<tr class="pipeline-program">` rows with `data-name`,
`data-code`, `data-therapeutic-area`, `data-modality`, `data-phase` (pipe list
of phase slugs per indication) attributes, and nested
`.pipeline-program-indication` blocks (title, phase slug, NCT-ID content, plus
a free-text mechanism-of-action paragraph per program). No Playwright/browser
automation needed for MSD, unlike Novo Nordisk.

One DOM quirk found and worked around: each program row renders its
indications **twice** — once in a `.pipeline-program-indications` div
(mobile layout) and once in a nested `<table>` (desktop layout). Selecting
indications broadly (e.g. `tr.pipeline-program .pipeline-program-indication`)
double-counts every row; `scrape_pipeline.py` reads only the
`.pipeline-program-indications` copy.

**Coverage decision** (confirmed with user): the webpage's own phase filter
only offers Under Review / Phase 3 / Phase 2 — no Phase 1 (consistent with
the PDF's page-1 disclaimer that Phase 1 candidates are deliberately
excluded) and no "Approved" phase. The PDF has a small separate "Approvals"
page (4 items, footnote: "obtained within the last 3 months") not present on
the webpage at all. Cross-checking those 4 against the webpage found all 4
compounds already listed there too, but for *different* indications/regions
(e.g. clesrovimab/ENFLONSIA is EU-approved for RSV per the PDF, while the
webpage's RSV row for the same compound is still "Under Review" — a genuine
region-level regulatory-status split, not a duplicate). Resolved by keeping
both: the webpage's own row plus a new `Registered`-phase row (hand-
transcribed from the PDF, tagged with its own `Region:` in `others`).

## Row counts (verification)

- 36 distinct `tr.pipeline-program` rows on the webpage → 105 asset×indication
  rows after exploding by indication (verified indication-div count against
  each row's `data-phase` pipe-list length — 0 mismatches across all 36).
- + 4 hand-transcribed rows from the PDF's Approvals page (page 7 of the PDF)
  = **109 total rows**, matching `msd_pipeline.parquet`.
- Phase breakdown: Phase 2 = 58, Phase 3 = 35, Preregistration = 12,
  Registered = 4.
- User cross-checked all 36 molecule names and their full indication lists
  against a manual copy of the live page's table — confirmed all 36 present
  with matching indication counts, and this surfaced the two bugs documented
  above (missing per-indication region tags for 12 rows, and the MK-3475A
  `data-name` typo), both fixed and re-verified after the fact.

## Field-mapping decisions (confirmed with user)

- **Row granularity**: one row per (asset, indication) pair — matches the
  Roche/GSK/Novo Nordisk convention. The webpage already structures data this
  way natively (one `.pipeline-program-indication` block per indication),
  so no manual explosion of a combined field was needed like Roche/Novo.
- **asset_name**: the webpage's visible program-name heading (already the
  resolved generic/brand/code label — some programs have no generic name
  assigned yet and the heading is just the MK-/V-code, e.g. `MK-1167`). The
  MK-/V-code (`data-code`) goes into `synonyms` when it differs from
  `asset_name`. Trademark symbols (®/™) and a stray `**` marker seen in a
  couple of name/code values were stripped as pure rendering noise, not a
  mapping ambiguity.
- **`data-name` HTML attribute vs. visible heading** (bug found and worked
  around, not a mapping decision): initially read `data-name` directly, which
  is correct for 35/36 programs but reads `"KEYTRUDAA"` for MK-3475A — a bug
  in MSD's own markup. The *visible* heading for the same row correctly reads
  `"KEYTRUDA QLEX™"`, matching the PDF's name for that code. `scrape_pipeline.py`
  now reads the visible `.pipeline-program-name` heading instead of the
  attribute for every program (confirmed by diffing all 36: only MK-3475A
  differed). The MoA text's separate forward-looking rename footnote ("to be
  marketed under the trade name KEYTRUDA SC in the EU", not yet in effect) is
  kept as an extra synonym, `synonyms = ["MK-3475A", "KEYTRUDA SC"]`.
- **mechanism_of_action**: 34 of 36 programs have an explicit
  `"Mechanism of Action: ..."` labelled sentence in the program's free-text
  blurb — used directly (label stripped, first sentence after it). The
  remaining 2 (`raludotatug deruxtecan`, `V181`) have no label; fell back to
  the Roche-precedent regex (first `"<X> is a/an ..."` sentence). Any
  remaining text in the blurb (acquisition/partnering/combination notes, e.g.
  "acquired as part of the acquisition of Prometheus Biosciences, Inc.") goes
  into `notes`.
- **therapeutic_area**: kept verbatim from `data-therapeutic-area`
  (title-cased, e.g. `oncology` → `Oncology`), consistent with the
  keep-source-labels-verbatim convention. For the 4 PDF-only Approvals rows
  (which have no therapeutic-area attribute of their own), backfilled from
  the matching webpage program's own `data-therapeutic-area`.
- **phase mapping**: `phase-2`→`Phase 2`, `phase-3`→`Phase 3`,
  `under-review`→`Preregistration` (matches the GSK/Novo Nordisk
  filed/under-review precedent), PDF Approvals page→`Registered`.
- **Region handling**: indication titles that embed a trailing region tag
  (e.g. `"Small cell lung cancer (EU)"`, `"Hematological malignancies (US)"`)
  have the tag stripped into `others` as `"Region: EU"` — keeps `indication`
  text comparable across companies. The 4 PDF Approvals rows get their own
  `Region:` entry the same way (one is `"US, JPN"` since the PDF box tagged
  both). **Second region source found after initial pass**: 12 of 105
  indications carry their region not in the title but in a separate
  `.pipeline-phase-bars .pipeline-phase-text` node (e.g. `"Under Review
  (JPN)"`, rendered as status text instead of plain progress-bar dots) —
  missed on the first scrape since only the title and NCT-content elements
  were read. `scrape_pipeline.py` now captures this text too, and the
  converter checks it whenever the title itself has no region suffix. Caught
  by a user spot-check against a full copy of the live page's table, which
  showed `(JPN)`/`(US)`/`(EU)` status tags for e.g. ENFLONSIA/KEYTRUDA/WELIREG
  rows that the first-pass `raw_pipeline.json` didn't have.
- **Multi-NCT indications**: content field often lists a trial acronym plus
  several NCT numbers (e.g. `"CORALreef Lipids; NCT05952856, CORALreef HeFH;
  NCT05952869, ..."`). First NCT number found → `trial_id`; the full raw text
  → `others` as `"Trials: ..."` (nothing dropped).
- **PDF Approvals rows without a webpage-sourced NCT match**: `KEYTRUDA QLEX`
  / `MK-3475A`'s ovarian-cancer approval (KNB96) has no matching indication on
  the webpage's MK-3475A program at all (its 3 webpage indications are
  bladder/breast/hematological, not ovarian) — `trial_id` left null for that
  one row, study code `KNB96` kept in `others` instead of guessing an NCT
  number.

## Data-quality anomalies found (flagged, not silently fixed)

- `"KEYTRUDAA"` (MK-3475A `data-name` attribute bug) — see above; resolved by
  reading the visible heading instead, not by patching the string.
- `"Platinum-resistant recurrent ovarian  cancer"` (double space) and
  inconsistent capitalization between the webpage's and PDF's versions of the
  same indication text for KEYTRUDA/MK-3475 — left as-is per source, not
  normalized (casing/whitespace normalization is out of scope until more
  companies are loaded, same as `therapeutic_area`).
- Region-level regulatory-status divergence for the same drug+indication
  (webpage shows "Under Review", PDF shows already "Approved" for a different
  region) is real, not a data error — see Coverage decision above for how
  it's represented (two separate rows, each with its own `Region:` tag).

## Files

- `msd_pipeline_2Q2026.pdf` — official quarterly pipeline PDF (2Q2026,
  reflecting pipeline to 30-Apr-2026), kept for provenance/cross-check.
- `scrape_pipeline.py` — pass 1: fetches the live pipeline page (fully
  static HTML, no browser needed), parses `tr.pipeline-program` rows into
  105 unmapped rows, appends 4 hand-transcribed PDF Approvals-page rows →
  `raw_pipeline.json` (109 rows total). Also saves the fetched HTML as
  `msd_pipeline_page.html` for provenance.
- `msd_to_parquet.py` — pass 2: maps `raw_pipeline.json` onto
  `PipelineRecord` (imported from `schema` per the shared-schema convention)
  → `msd_pipeline.parquet`.
- `raw_pipeline.json`, `msd_pipeline_page.html` — raw scrape output.
- `msd_pipeline.parquet` — 109 records.

## Dependencies added

`beautifulsoup4` (HTML parsing) and `pdfplumber` (PDF cross-check/positional
inspection) added to `pyproject.toml` via `uv add` — not previously in the
project's uv env. Both are reusable for the remaining Tier 2 "chart" PDFs
(Amgen, BMS) still `TODO`.
