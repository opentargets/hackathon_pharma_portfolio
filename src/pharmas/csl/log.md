# CSL — extraction log

Tier 3 in `docs/sources.md` ("You have to interact to extract the
indication"). Tracked in GitHub issue [#32](https://github.com/opentargets/hackathon_pharma_portfolio/issues/32).

## Source discovery

Checked both possible source types before trusting the Tier 3 label, per
`instruction_for_agent.md`:

- **File**: no dedicated pipeline PDF/CSV exists for CSL. Checked
  `csl.com/research-and-development` and `investors.csl.com` — the only PDF
  found was a general "Capital Markets Day" investor presentation, not a
  pipeline table, so not used.
- **Webpage** (`https://www.csl.com/research-and-development/product-pipeline`):
  cheap `curl` (no browser, no cookies) returns the complete dataset already
  in the HTML. **The Tier 3 "you have to interact" label in `docs/sources.md`
  is stale/wrong** — same pattern as MSD before it. Each pipeline item's
  "popup" content (the text shown when you click it) is already inline in
  the raw HTML inside a `<p class="p-content">` tag, just visually hidden
  until clicked — the HTML comment literally reads
  `<!-- product popup content-->` right above it. User initially thought
  clicking a drug reveals *more* information than the static page; the
  example they pasted (TS23) matched exactly what the static-HTML parse
  already had, confirming no interaction is needed.

Used the webpage only (confirmed with user — no PDF exists to merge with).

## Row counts (verification)

- 34 `<a class="p-item">` elements on the page, all inside one category
  section ("CSL R&D Portfolio – FY25"), across 4 phase buckets: Phase I (1),
  Phase II (8), Phase III (6), Registration/Post Registration (19).
- `scrape_pipeline.py` extracted exactly 34 rows — matches a manual `grep -c
  'class="p-item"'` count on the raw HTML.

## Field-mapping decisions (confirmed with user)

- **asset_name**: kept the full source label string verbatim, no attempt to
  regex-split it into a separate code/generic/brand identifier — CSL's
  labels are too inconsistent for that (mix of internal codes like `CSL040`,
  INNs like `Vamifeport`, and branded names like
  `HIZENTRA®(SCIg) 20% Liquid (SID)`, sometimes with a trailing indication
  abbreviation in parens).
- **synonyms**: for labels containing a `®` mark, the brand token(s) before
  each `®` are pulled into `synonyms` (e.g. `HIZENTRA` out of
  `HIZENTRA®(SCIg) 20% Liquid (SID)`). Handles the dual-brand case where the
  same product is marketed under two names in different regions (e.g.
  `ZEMAIRA®/RESPREEZA®...` → `synonyms = ["ZEMAIRA", "RESPREEZA"]`). Non-`®`
  labels (code names, INNs) get no synonyms.
- **mechanism_of_action / indication**: source gives one free-text blurb per
  row with no separate MoA/indication columns. Split via a regex tier of
  connector phrases ("for the treatment of", "to treat", "for protection
  against", "for prophylactic use in", "used for the control of", etc.) —
  text before the connector → `mechanism_of_action`, text after →
  `indication`. A second, looser tier ("in adults with" / "in patients
  with") catches a few stragglers (e.g. ZEMAIRA's "...therapy in adults with
  A1-PI deficiency and emphysema"). **5 of 34 rows have no matching
  connector at all** — `VMX-C001 rFX (FXa Inhibitor Bypass)*`, `TS23
  Anti-α2AP mAb (sPE)*`, `Horizon 2 Ig Yield`, `KOSTAIVE®sa-mRNA Vaccine
  (COVID)`, `CSL403 (aTIVc) Adjuvanted Cell-based Trivalent Influenza
  Vaccine` — for these, `mechanism_of_action` is left null and the entire
  blurb goes into `indication` unsplit, per the fallback approved by the
  user. (Separately, a few rows like `CSL404`/`AUDENZ`/`FLUCELVAX` also end
  up with a null `mechanism_of_action` even though a connector *did* match —
  those blurbs are legitimately indication-only sentences starting with "For
  protection against...", so there's no MoA text before the connector to
  begin with; not a fallback case.)
- **therapeutic_area**: kept verbatim from the page's own 5 filter-checkbox
  labels (Immunoglobulins, Hematology, Cardiovascular & Renal, Transplant &
  Immunology, Vaccines), matched via each item's `data-filter` UUID. No
  normalization to a shared vocabulary yet, consistent with other companies.
- **phase**: `Phase I`/`Phase II`/`Phase III` → `Phase 1`/`Phase 2`/`Phase
  3` directly. The 4th bucket, `Registration / Post Registration`, mixes
  pre-approval filings with already long-marketed/approved products (e.g.
  `FLUCELVAX`, `VELTASSA`) — CSL's own site doesn't separate them, and the
  shared schema has no "Marketed"/"Approved" phase value. **Confirmed with
  user (2026-07-09): map the whole bucket to `Registered`.**
- **trial_id**: left null for all rows — no NCT IDs anywhere on the CSL
  pipeline page.
- **`others`**: every row gets `"Pipeline data current as at: 26 May 2026
  (per CSL page footnote)"` — the page has a footnote stating the pipeline
  snapshot's freshness date, separate from `extraction_date` (the date this
  was scraped, 2026-07-09).

## Manual cross-check (2026-07-09)

User pasted a manual copy of the full pipeline page (all 34 names, in order)
plus the full AFSTYLA row (name, area, phase, content) copied straight off
the live page. Diffing against the first-pass `raw_pipeline.json` found a
real bug:

- **`get_text(strip=True)` dropped a space at every `<sup>®</sup>` tag
  boundary** — BeautifulSoup's `strip=True` strips each text node
  individually *before* joining them, with no separator inserted between
  nodes. CSL's own markup is `HIZENTRA<sup>&reg;</sup> (SCIg)...`; the space
  between `</sup>` and `(SCIg)` lives in a separate text node from `®` and
  was stripped away entirely, producing `HIZENTRA®(SCIg)...` instead of the
  correct `HIZENTRA® (SCIg)...`. Affected **22 of 34** `asset_name` values
  (every `®`-branded one except `FILSPARI` and `KORSUVA`/`KAPRUVIA`, which
  happen to have no space in the source markup at that position) plus 2
  `.p-content` mentions of `MF59®(an additive...` (FLUAD, FOCLIVIA).
  Fixed in `scrape_pipeline.py` by extracting text without `strip=True`
  (whitespace normalized afterwards instead of per-node), added as a
  `clean_text()` helper. Re-scraped, re-mapped, and re-verified against the
  user's pasted list — all 34 names now match exactly, in order. The
  AFSTYLA row's full field set (area, phase, content) also matched exactly.
- This is exactly the class of bug the required user cross-check step exists
  to catch — invisible from re-reading the raw HTML text dump, since the
  bug is in how it's *parsed*, not in the source itself.

## Data-quality anomalies found (flagged, not silently fixed)

- **Page footnote not attached to any pipeline item** — easy to miss if only
  the `.product-pipeline` section is parsed. The page has a
  `<section class="footnotes">` below the table with two `<p>`s: a
  `*`-marker explainer (`"Co-development project; partner owned asset with
  exclusive option rights held by CSL"`, applying to the 2 assets whose name
  ends in `*` — `VMX-C001` and `TS23`) and the "current as at 26th May 2026"
  freshness note. `scrape_pipeline.py` now captures both explicitly; the
  co-development note is attached to the two `*`-marked rows' `notes` field.
- **5 rows with no MoA/indication connector** (`VMX-C001`, `TS23`, `Horizon 2
  Ig Yield`, `KOSTAIVE`, `CSL403`) — see mapping decision above. `Horizon 2
  Ig Yield` in particular isn't really a disease-indication row at all (it's
  a manufacturing/process-improvement program, "novel technologies to
  optimise processes for increased Ig yield") — kept as-is in `indication`
  since the schema has no better field for it and CSL itself lists it
  alongside actual drug candidates in Phase III.
- **`docs/sources.md`'s Tier 3 note was stale** — see Source discovery above.

## Files

- `scrape_pipeline.py` — pass 1: fetches the live pipeline page (fully
  static HTML, no browser/interaction needed), parses `a.p-item` elements
  grouped by `.category-phase` into 34 unmapped rows plus page footnotes →
  `raw_pipeline.json`. Also saves the fetched HTML as `csl_pipeline_page.html`
  for provenance.
- `csl_to_parquet.py` — pass 2: maps `raw_pipeline.json` onto `PipelineRecord`
  (imported from `schema`, not copied) → `csl_pipeline.parquet`.
- `raw_pipeline.json`, `csl_pipeline_page.html` — raw scrape output.
- `csl_pipeline.parquet` — 34 records.
