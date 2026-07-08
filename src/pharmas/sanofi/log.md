# Sanofi extraction log

Source: https://sanofi.com/en/our-science/our-pipeline
(Tier 3 per docs/sources.md: JS-rendered interactive tracker, "77 clinical-stage projects (2026)".)

## 0. Source verification (before trusting the tier label)

Per instruction_for_agent.md, checked both possible sources before deciding, rather
than assuming the Tier 3 label or the downloaded file was the right pick:

- **Downloadable file**: user had downloaded `sanofi-q1-2026-results.pdf`, Sanofi's
  Q1 2026 investor results deck (not a dedicated pipeline document). It does contain
  a phase-by-phase pipeline appendix (pages 31-34: Registration/Phase 3/Phase 2/Phase 1,
  plus licensing-stage assets) and a "main clinical studies" NCT-ID list (pages 40-41),
  but:
  - The phase-by-phase pages are a multi-column positional grid (`pdfplumber` text
    extraction interleaves columns), similar parse-risk to Amgen's flagged "chart" PDF
    in docs/sources.md, not a literal table.
  - It's a point-in-time investor snapshot ("As of March 31, 2026"), not the canonical
    pipeline page.
- **Webpage**: `curl`ed first (cheap check before reaching for a browser) -- HTTP 200
  but the raw HTML is a fully client-rendered React/MUI/Vite SPA with no embedded
  `__NEXT_DATA__`/ld+json/inline JSON blob. Confirms genuine Tier 3 (unlike MSD, which
  looked dynamic but turned out to be static on `curl`).
- **User decision: scrape the webpage only.** The PDF's grid pages were judged too
  parse-risky and non-canonical; the webpage is the dedicated, complete tracker.

## 1. Page structure (discovered via rendered-HTML inspection, not blind clicking)

Rendered with headless Playwright (`networkidle` + dismiss OneTrust cookie banner),
then inspected the resulting DOM rather than assuming a click-driven widget like
Novo Nordisk's:

- Each clinical-stage project is one row with **Name / Phase / Description (free-text
  MoA) / Therapeutic Area / Indication already static in the DOM** -- no click needed
  for those 5 fields, unlike Novo Nordisk where the description only appeared after
  clicking into a modal.
- Phase is shown as four badges ("1", "2", "3", "R"); the *current* phase is the one
  with a purple-filled badge (`.css-yaszgn-MuiTypography-root`, confirmed via
  `getComputedStyle` -- white text on `rgb(35, 0, 76)` background) vs the unfilled
  badge (`.css-3ha4an-MuiTypography-root`, dark text on white).
- Every row renders **twice** -- once in a labelled block, once in an unlabelled
  responsive-duplicate block, both sharing the same
  `aria-label="Expand details for <name> in <indication>"` button on the "Expand
  details" control. Exactly the same mobile/desktop duplication pattern as MSD.
  Filtering to `is_visible()` buttons narrows 154 -> 77, matching docs/sources.md's
  stated project count exactly (see Section 3 phase tally below, which also lines up
  1:1 with the PDF's own "Registration" section, see Section 4).
- Clicking a row's "Expand details" button (confirmed worth doing with the user)
  reveals 3 more fields not present in the static DOM: **Collaboration** (e.g.
  "Developed in collaboration with Regeneron"), **Notes** (often "Also known as
  <code>", sometimes other free text), and **Expected Submission Timeline**. These
  mount into the DOM only on click (conditionally-rendered accordion, not just
  CSS-hidden), and as a *sibling* of the row's own summary block a couple of DOM
  levels up -- not nested inside it -- so the scraper has to climb past the first
  matching ancestor rather than stopping there (see `scrape_pipeline.py`'s
  `ROW_CONTAINER_JS` comment for the exact heuristic: climb while a second
  "Description" occurrence hasn't appeared yet, which would mean overshooting into
  the multi-row list container).

## 2. Scraping approach

`scrape_pipeline.py` -- plain Playwright (via scrapling's installed browser deps),
headless Chromium, viewport 1440x900 (desktop layout, so the labelled/visible copy of
each duplicated row is deterministically the one picked up):
1. Load page, dismiss cookie banner, wait for network idle.
2. Enumerate all `[aria-label^="Expand details for"]` buttons, keep only the 77 that
   are `is_visible()`.
3. For each: locate its row container (climb-while-single-row heuristic above),
   snapshot outerHTML, click, wait 400ms, snapshot outerHTML again.
4. Parse both snapshots with BeautifulSoup via a shared `field_value()` helper: every
   field on this page renders as N sibling `<p>` tags where the **last** one is
   always the value (2 siblings for static fields: label+value; 3 for expanded
   fields: mobile-label+desktop-label+value) -- this is robust to Emotion's
   hashed class names, unlike matching on `css-xxxxx` classes directly.

Output: `raw_pipeline.json` / `.csv`, 77 rows, unmapped.

## 3. Verification against the source

- Row count: 77, exactly matching docs/sources.md's "77 clinical-stage projects (2026)".
- Phase tally: Phase 1 = 15, Phase 2 = 28, Phase 3 = 28, Registration ("R") = 6.
- No `None`/missing values in name, description, therapeutic_area, or indication
  across all 77 rows.
- Only one true `(name, indication)` collision: **SP0287** appears twice under
  "Flu+COVID-19" -- these are two distinct vaccine-combination formulations
  ("Flublok+Nuvaxovid" vs "Fluzone HD+Nuvaxovid"), distinguishable via
  `mechanism_of_action` even though `asset_name`+`indication` collide. User confirmed
  accepting the collision rather than disambiguating the name.
- A parallel `aria_label_name`/`aria_label_indication` pair was scraped as an
  independent audit trail. 7/77 rows show a cosmetic mismatch against the
  DOM-extracted `name`/`indication` -- all are just the audit field's naive
  `" in "`-split regex splitting on the wrong occurrence of "in" when the indication
  text itself contains the word "in" (e.g. "Geographic atrophy **in** dry
  age-related macular degeneration" split at the first "in"), or trailing
  whitespace. The actual `name`/`indication` fields (extracted structurally from the
  labelled DOM blocks, not via string-splitting the aria-label) are correct in all 7
  cases -- this is noise in the debug-only field, not a data quality issue.
- **Cross-checked Collaboration data against the PDF's independent "Collaborations"
  table** (`sanofi-q1-2026-results.pdf`, page 42, not used as the primary source but
  available for corroboration): frexalimab/ImmuNext, itepekimab/Regeneron,
  rovadicitinib/Sino Biopharma(m), Dupixent/Regeneron, duvakitug/Teva
  Pharmaceuticals, SAR445953/Pfizer, SP0202/SK Bioscience -- all 7 overlapping pairs
  agree (only cosmetic casing/spelling differences, e.g. "Sino Biopharm" vs "Sino
  Biopharma"). No inconsistency found.
- The Registration ("R") set of 6 assets (Dupixent BP EU, Tzield T1D stage 3 US,
  Wayrilz ITP JP, tolebrutinib SPMS US/EU, Sarclisa MM, Fluzone HD flu 50y+ US/EU)
  matches the PDF's own "Registration" section (page 31) name-for-name.

## 4. Schema mapping (`sanofi_to_parquet.py`)

Confirmed interactively, decisions:

- `asset_name` = `name` verbatim. One combo-therapy row keeps the source's own
  comma-joined string as-is (`"frexalimab, rilzabrutinib, brivekimig"`, Phase 2 FSGS
  / minimal change disease) rather than being split into 3 rows -- the source
  presents it as a single program.
- `mechanism_of_action` = `description` verbatim (already an isolated column on this
  source, e.g. "IL33 mAb", "CD28xOX40 bispecific Ab" -- no free-text splitting
  needed, unlike Novo Nordisk).
- `therapeutic_area` = source's own label verbatim (Immunology / Vaccines / Rare
  Diseases / Neurology / Oncology -- already title-cased).
- `indication` = source's own label verbatim.
- `phase`: `1`/`2`/`3` -> `Phase 1`/`Phase 2`/`Phase 3` directly. `R` (Registration)
  -> `Preregistration` (filed/under review, not yet approved -- confirmed against the
  PDF's own "Registration" section semantics and consistent with the GSK/Novo
  Nordisk precedent for this exact "filed" situation).
- `synonyms`: parsed out of the scraped Notes field via regex on "(also|formerly)
  known as X", where X is always a single compound-code-like token in this source
  (e.g. "SAR441566", "INBRX-101", "BLU-808") -- matching that token shape rather than
  "everything up to the next comma/period" avoids swallowing unrelated trailing text
  (caught during testing: "Also known as MAB212, in-licensed from MAB Discovery"
  would otherwise wrongly capture the whole tail as part of the synonym).
- `notes` = Collaboration text + any Notes leftover after the synonym regex has been
  stripped out (e.g. "in-licensed from MAB Discovery", "Approved in EU"), joined with
  "; " -- matches the schema's own notes examples ("Partnered with X").
- `others` = `["Expected Submission Timeline: <value>"]` when a real value exists;
  the "Not available yet" placeholder (59/77 rows) is dropped as noise rather than
  carried through.
- `trial_id` = null for all rows -- this source has no NCT IDs (the PDF's "main
  clinical studies" appendix, pages 40-41, does have them, but that source wasn't
  used per the user's webpage-only decision).
- Collision handling: SP0287's 2 rows keep identical `asset_name`+`indication`
  (user-confirmed) -- distinguishable via `mechanism_of_action`.

Output: `sanofi_pipeline.parquet` (77 rows).

## 5. User manual cross-check

User copy/pasted the full rendered table (77 rows: Therapeutic Area / Phase badges /
Name / Description / Indication) directly from the live page, plus the expanded
detail panel (Collaboration/Notes/Expected Submission Timeline) for 3 specific rows
(SP0218 Yellow fever, Sarclisa ITHACA, itepekimab COPD).

Diffed programmatically against `raw_pipeline.json`:
- All 77 rows matched **exactly** in name, description (MoA), indication, therapeutic
  area, and row order. The only apparent mismatch (`SAR444336`'s "Synthorin™" vs
  "Synthorin(TM)") was a transcription artifact in how the cross-check text was typed
  into a shell heredoc, not a real discrepancy -- confirmed by checking the original
  scraped value against the pasted Unicode.
- All 3 spot-checked expanded-detail rows matched exactly:
  - SP0218/Yellow fever: notes=null, others=["Expected Submission Timeline: 2027"].
  - Sarclisa/ITHACA: notes=null, others=null (source said "Not available yet",
    correctly dropped per the user's earlier decision).
  - itepekimab/COPD: notes="Developed in collaboration with Regeneron",
    others=["Expected Submission Timeline: subject to further analysis and decision"].

**No inconsistencies found.** Sanofi's extraction is clean on first pass -- no bugs
surfaced by this cross-check, unlike MSD (2 bugs found post-hoc by the same kind of
check).
