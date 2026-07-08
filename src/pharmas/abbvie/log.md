# AbbVie extraction log

Source: https://www.abbvie.com/science/pipeline.html
(Filed as Tier 4 in docs/sources.md: "Narrative text per therapeutic area... No
single structured source." — that label was stale, see Section 0.)

## 0. Source verification (before trusting the tier label)

Per instruction_for_agent.md, checked both possible sources before deciding:

- **Downloadable file**: no pipeline PDF/CSV exists. The only two PDFs linked from
  the pipeline page are `pricing-and-access-of-our-innovative-medicines.pdf`
  (pricing policy) and `abbvie-esg-action-report.pdf` (2025 ESG report) — neither
  is pipeline data.
- **Webpage**: plain `curl` (cheap check first) returns HTTP 403 — Cloudflare
  "Attention Required!" challenge page, not the real content. Fetched instead via
  `scrapling`'s `StealthyFetcher` (browser-based, passes the Cloudflare check with
  no explicit challenge needing solving — `[ERROR] No Cloudflare challenge found`
  logged, meaning a normal browser fetch was already enough).
  Once past Cloudflare, the page is **not narrative prose** — it's a filterable
  pipeline search tool where every asset is a `div.cmp-pipeline` element with the
  full record embedded as static `data-*` attributes (`data-title`,
  `data-asset-focus-area`, `data-asset-type`, `data-asset-target`,
  `data-asset-description`, `data-asset-indication`, `data-asset-phases`), plus a
  nested per-indication table giving indication / region / phase-status per row.
  No click-to-reveal interaction is needed to get any of this — unlike Novo
  Nordisk/Sanofi where data only appears after clicking each item, here Cloudflare
  is the only gate between `curl` and the full dataset.
- **User decision: webpage is the sole source**, treated with the Tier-3-style
  two-pass workflow (scrape raw, then map) since a browser fetch was required to
  get past Cloudflare, even though no click-loop was needed once fetched.
  docs/sources.md's Tier 4 label corrected to reflect this.

## 1. Page structure

- 57 top-level asset cards: 51 `data-type="pharmaceutical"` + 6
  `data-type="devices"` (all 6 are Aesthetics/facial-filler products).
- 97 asset x indication rows total (one asset can list multiple indications, each
  with its own phase/region) — close to the page's own "~90 compounds, devices or
  indications in development" hero stat (reads as AbbVie's own rounded figure, not
  a scraper undercount — see Section 3).
- Every indication row renders **twice** — a `desktop-element` copy and a
  `mobile-element` copy of the region/phase-status cells — same
  mobile/desktop-duplication pattern seen on MSD and Sanofi. Only the
  `desktop-element` copies were read to avoid double-counting.
- Pharma assets use phase-status classes `phase1`/`phase2`/`phase3`/
  `submitted`/`approved`. Device assets use a distinct scale
  (`concept`/`feasibility`/`development`/`confirmation`/`approved`/`launched`) —
  in the live data only `confirmation` and `approved` actually occur.
- **Anomaly (source-side inconsistency)**: the "no region" placeholder renders as
  two different literal strings depending on the row — `"N ∕ A"` (U+2215 DIVISION
  SLASH character, most rows) vs `"N A"` (no slash at all, e.g. the HArmonyCa
  device row). Both were treated as "no region" during mapping (see Section 4).
  Also, populated multi-region values render with a stray space before the comma
  (`"US , EU"` instead of `"US, EU"`) — normalized to `"US, EU"` when carried into
  `others`.

## 2. Scraping approach

`scrape_pipeline.py` — single `scrapling.fetchers.StealthyFetcher.fetch()` call
(no click-loop, no Playwright script needed, since all data is already static in
the DOM once Cloudflare is passed):
1. Fetch the page, select all `div.cmp-pipeline[data-title]` elements (57 cards).
2. For each card, read the asset-level `data-*` attributes directly.
3. For each nested `.phases-section .phase-element .phases-container` row, read
   indication (`div.col1 span.phase-title`), region
   (`div.col2.desktop-element span.region-label`), and phase-status
   (`div.col3.desktop-element span.phase-status`, class name minus the
   `phase-status`/`desktop-element` tokens).
4. Normalize whitespace and the `∕` (U+2215) division-slash character to a plain
   `/` while parsing.

Output: `raw_pipeline.json` / `.csv`, 57 assets / 97 flat indication rows,
unmapped.

## 3. Verification against the source

- 97 `phase-title` (indication row) elements in the raw HTML exactly match 97
  rows extracted by the scraper — no rows dropped or duplicated.
- Asset-type split: 51 pharmaceutical + 6 devices, matching the raw HTML's
  `data-type` attribute count exactly.
- Focus-area tally: Oncology 19, Immunology 14, Neuroscience 11, Aesthetics 8, Eye
  Care 3, Other Specialties 2 (from `data-asset-focus-area`, asset-level, not
  row-level).
- No `None`/missing values in `data_title`, `data_asset_focus_area`, or
  `data_asset_indication` across all 57 assets.

## 4. Schema mapping (`abbvie_to_parquet.py`)

Confirmed interactively with the user before writing the converter, decisions:

- `asset_name` = `data_title` verbatim, including combo-name parentheticals
  (e.g. `"ABBV-166 (SKYRIZI + Lutikizumab)"`). No collisions found across the 57
  assets.
- `mechanism_of_action` = `data_asset_target` (the short target string, e.g.
  "LPAR1", "IL-23 + IL-1a/1b") rather than the long free-text description
  paragraph, for consistency with how other companies' `mechanism_of_action` was
  populated (short mechanism string, not a full paragraph). Left `None` when the
  source's own value is the literal `"N / A"` placeholder (6 rows) rather than
  carrying that string through.
- `therapeutic_area` = `data_asset_focus_area` verbatim (already Title Case
  matching AbbVie's own display) — not normalized to a shared vocabulary yet, per
  the standing rule.
- `indication`, `phase`, `region` all read per-row from the nested phase table,
  **one `PipelineRecord` row per asset x indication combo** (e.g. ABBV-319 → 2
  rows, one for SLE and one for Sjogren's disease, since they can carry different
  phases/regions independently) rather than collapsing an asset to a single row.
- `phase` mapping:
  - Pharma: `phase1`/`phase2`/`phase3` → `Phase 1`/`Phase 2`/`Phase 3` directly;
    `submitted` → `Preregistration`; `approved` → `Registered`.
  - Devices (distinct scale, schema has no device-specific phase concept):
    `confirmation` → `Phase 3` (closest analog — last pre-approval stage);
    `approved` → `Registered`. `concept`/`feasibility`/`development`/`launched`
    don't occur in the current data, so no mapping was needed for them, but if
    they appear in a future refresh they'd need the same treatment before
    re-running the converter.
- `modality`: `data_asset_type` for pharma rows (Biologic/Small Molecule/Large
  Molecule/Gene Therapy). For device rows, `data_asset_type` is always the
  literal `"N / A"` string, so `modality` is hardcoded to `"Device"` instead
  (the real signal is the `Device` entry in `data_asset_tags`, not
  `data_asset_type`).
- `notes` = `"Combination therapy"` when `asset_name` contains a literal `"+"`
  (e.g. "ABBV-166 (SKYRIZI + Lutikizumab)"), else `None`. **Caught during
  spot-checking**: an earlier version of this rule also fired on any
  parenthetical (`\(.*\)`), which wrongly tagged plain "Generic Name (ABBV-code)"
  pairs like "Icalcaprant (ABBV-1354)" as combination therapies — fixed to only
  match on `"+"` before the parquet was finalized (see `abbvie_to_parquet.py`
  history / this was not committed in the buggy form).
- `others` = `["Region: <value>"]` when a real region exists (populated only on
  Submitted/Approved-adjacent rows: US, EU, JA, CN, OUS, or combinations); `None`
  for the "N/A" placeholder rows (both `"N ∕ A"` and the inconsistent `"N A"`
  spelling are treated as no-region).
- `synonyms` = `None` for all rows — no separate brand-name/INN column exists
  beyond `asset_name` itself.
- `trial_id` = `None` for all rows — this source has no NCT IDs.

Output: `abbvie_pipeline.parquet` (97 rows).

## 5. User manual cross-check

User copy/pasted the rendered pipeline tool directly from the live page, covering
all 6 focus areas (Immunology, Neuroscience, Oncology, Eye Care, Aesthetics,
Other Specialties) — i.e. the entire pipeline, not a sample — plus an explicit
follow-up request to verify 3 specific assets' Target/Type of molecule/Phase
fields (Armour Thyroid, ABBV-711, ABBV-1042).

Diffed programmatically against `raw_pipeline.json`:
- **Asset completeness**: all 57 asset names in the paste exactly match the 57
  scraped asset names — no assets missing on either side (`set` diff empty both
  ways) — and in the **same order**, focus-area by focus-area.
- **3 specifically-flagged assets**, all matched exactly:
  - Armour Thyroid: target T3T4, modality Biologic, phase Phase 3.
  - ABBV-711: target N/A (-> `mechanism_of_action=None` per Section 4's rule),
    modality Small Molecule, phase Phase 1.
  - ABBV-1042: target M4 Receptor, modality Small Molecule, phase Phase 1.
- **Multi-indication assets spot-checked in full** (RINVOQ 13 indications,
  EPKINLY 7, BOTOX 3, ABBV-706 3): every indication/region/phase-status triple
  matches. Notably, several rows (RINVOQ's Hidradenitis Suppurativa/SLE/Takayasu
  Arteritis, ABBV-706's Neuroendocrine Neoplasms) show **no visible
  "phase1"/"phase2"/"phase3" text label** in the copy/pasted page content — only
  the colored progress-bar segment renders visually, with the text label
  present in the DOM but not in a form that plain copy/paste picks up. The
  scraper reads the underlying CSS class (`phase-status phase3`, etc.) directly
  from the DOM rather than relying on visible text, so it correctly captured
  these phases even though they're invisible to a manual copy/paste check —
  this cross-check could not have caught a scraper bug in exactly these rows
  since the "ground truth" text isn't copy/paste-visible either, but the target/
  region/other-indication values checked in the same rows agreed as an
  indirect validity signal.
- One paste-only artifact, not a scraper issue: BOTOX's "Masseter Prominence"
  row visually pasted as `"CN N ∕ A approved"` (both a real region and the N/A
  placeholder concatenated on one line) — an artifact of the page's
  duplicated desktop/mobile region spans both landing in the copy/paste buffer
  without a line break. The scraper's `raw_pipeline.json` correctly captured
  only the `desktop-element` copy (`region="CN"`), matching AbbVie's own visual
  rendering.

**No inconsistencies found.** AbbVie's extraction is clean on first pass — no
bugs surfaced by this cross-check, unlike MSD (2 bugs found post-hoc by the
same kind of check).
