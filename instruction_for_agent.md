# Instructions for the extraction agent

Distilled from three completed extractions: Roche (Tier 1, clean CSV), GSK
(Tier 2, xlsx), Novo Nordisk (Tier 3, JS widget, scraped). Follow this workflow
for every remaining company in `docs/sources.md`.

## Ground rules

- **One pharma at a time.** Don't start the next company until the current one
  has a parquet output, a log.md, and (if scraped) a closed-out GitHub issue.
- **Deterministic before scraping.** Prefer a structured source (CSV/xlsx/PDF
  table) over browser automation whenever one exists. Only fall back to
  scraping for Tier 3 (JS-widget) sources.
- Check `docs/sources.md` for the company's tier and any notes before starting.

## Repo layout

The project is a proper `src`-layout Python package (`pyproject.toml` has
`[build-system]` + `[tool.setuptools]` pointing at `src/`, installed editable
via `uv sync`). The shared `PipelineRecord` model + `Phase` enum live in
**one place**, `src/schema.py` (`model_config = {"extra": "allow"}`, so
source-specific extra fields like `others` can still be passed even though
they're not declared on the model) — don't copy `schema.py` into each
company's folder anymore (that was the pattern for Roche/GSK before the repo
was restructured into a package; Novo Nordisk was migrated to match).

Every company gets `src/pharmas/<company>/` with:

- an `__init__.py` (empty, makes it an importable subpackage)
- the raw source file(s) (CSV/xlsx/PDF, or a scrape script + raw JSON/CSV dump
  for Tier 3)
- `<company>_to_parquet.py` (or `<company>_csv_to_parquet.py` /
  `<company>_xlsx_to_parquet.py`) — the converter, importing the schema with
  `from schema import Phase, PipelineRecord` (resolves to `src/schema.py`
  because of the package-dir mapping — works via `uv run python
  src/pharmas/<company>/<script>.py`, no `sys.path` hacking needed, as long as
  `uv sync` has been run at least once so the project installs itself
  editable)
- `log.md` — extraction + mapping decision log (see below)
- the resulting `<company>_pipeline.parquet`

If `from schema import ...` ever raises `ModuleNotFoundError`, check that
`pyproject.toml` still has a `[build-system]` table and re-run `uv sync` —
without it the project never installs itself editable and the top-level
`schema` module isn't importable (this broke once during the restructure and
was fixed by adding `[build-system]`).

## Workflow

### 1. Tier 1/2 (structured source already exists)

1. Check **both** possible source types before deciding, regardless of what
   the tier/notes in `docs/sources.md` say — they can be stale or incomplete
   (MSD was listed as "PDF, chart, Phase 1 not shown" but its live pipeline
   page turned out to have far richer per-indication data than the PDF, found
   only by checking):
   - A downloadable file (PDF/CSV/xlsx) — locate/confirm it (ask the user if
     it's not already in the folder).
   - The pipeline webpage itself — cheap `curl` it and check whether the data
     is already there statically (embedded JSON, or in this case a fully
     server-rendered table), even if `docs/sources.md` doesn't call this
     company Tier 3.
   Present what each source actually contains (fields, richness, coverage,
   any gaps) and **ask the user which to use** before proceeding — don't
   default to the file just because it's the deterministic-looking option.
   If both exist and both add real information (e.g. the file covers
   something the webpage doesn't, or vice versa, as with MSD's PDF-only
   "Approvals" page), **use both**, cross-check them against each other for
   agreement, and confirm the merge approach with the user before writing the
   converter.
2. Inspect the data: unique values per column, sample rows, obvious anomalies
   (transposed columns, ID collisions, duplicate headings, missing
   indication/MoA columns).
3. **Before writing the converter**, confirm field-mapping decisions with the
   user via targeted questions (batch up to 4 at once), informed by the actual
   data — never guess silently. Ambiguities that come up every time:
    - `asset_name`: which column is the real identifier (internal compound
      code vs. generic/trade name)? Collisions across rows are possible — ask
      whether to accept them or need a fallback.
      **Preference (confirmed 2026-07-08 for AstraZeneca, apply going forward):**
      use the compound code (e.g. AZD-prefix) or INN/generic name as `asset_name`.
      Put trade/brand names in `synonyms`.
      Strip trial/protocol name suffixes (e.g. "SERENA-6", "DESTINY-Breast05")
      from the asset name — they are not part of the compound identity.
   - `mechanism_of_action`: if there's no dedicated column, extract
     deterministically from free text (e.g. regex for "is a/an ..." or
     whatever pattern the source's prose actually uses — check first, don't
     assume the same regex works across companies).
   - `therapeutic_area`: keep the source's own label verbatim (or
     title-cased to match its own display casing) — don't normalize to a
     shared vocabulary yet; that's deferred until more companies are loaded.
   - `phase`: map obvious terms directly; for ambiguous ones (e.g.
     "Registration", "Filed") ask which of `Preregistration`/`Registered`
     fits based on how *that company's own site* uses the term — do not
     assume the same source term always maps the same way across companies.
   - Anything source-specific worth keeping but not in the base schema goes
     in `others` (array of `"Key: value"` strings) or `notes` (free text) —
     `PipelineRecord` allows extra fields (`model_config = {"extra": "allow"}`
     in `src/schema.py`), so passing `others=[...]` works even though it's
     not a declared field on the model.
4. Write the converter, run it, and spot-check a handful of rows against the
   original source by eye.
5. Write `log.md` documenting every mapping decision and any data-quality
   anomaly found (even if resolved) — don't silently fix anomalies, flag them
   and ask first if the fix isn't obvious.

### 2. Tier 3 (JS widget, needs scraping)

Split into two passes — don't conflate scraping with schema-mapping:

1. **Scrape raw data first**, unmapped. Tooling is already set up in this
   repo (`scrapling[fetchers]` in the uv env, browser binaries installed via
   `uv run scrapling install`, skill at `.claude/skills/scrapling/`) — reuse
   it, don't reinstall. **Before writing a click-loop script**, do a cheap
   `curl` of the raw page first and check for an embedded data blob
   (`__NEXT_DATA__`, `ld+json`, inline `<script>` JSON) or an API endpoint the
   widget calls — if the data's already there, skip the browser entirely. Only
   drop to raw Playwright (a scrapling dependency) once that's ruled out —
   scrapling's own quick-path Fetchers only handle static/Cloudflare-protected
   pages, not click-to-reveal interaction. Expect a cookie-consent overlay to
   block clicks until dismissed first.
   - Write `src/pharmas/<company>/scrape_pipeline.py`, dump every row's fields as
     scraped (name, area/category, phase, free-text description, whatever the
     source exposes) to `raw_pipeline.json`/`.csv` — no schema mapping yet.
   - Verify: manually list what should be on the page (or have the user
     confirm) and diff it against the scraped row count/names/order.
   - Open a GitHub issue documenting the scrape (source structure, tooling
     used, row count, any surprises) so this checkpoint survives even if the
     mapping pass happens later/separately.
2. **Then do the schema-mapping pass** exactly like Tier 1/2 (step 1 above),
   treating the raw JSON as the source. Update the same GitHub issue with the
   mapping decisions and close it once verified.

## Pagination

Pipeline pages distribute records across more than one fetchable unit in five known shapes. Missing any one of them silently drops molecules.

1. **URL pagination** — `?page=N`, `?p=N`, `?offset=&limit=`, etc. (e.g. Novartis).
2. **"Load more" / next-page button** — explicit click-to-paginate.
3. **Infinite scroll** — records mount as the user scrolls.
4. **Filter combinations** — union of every filter set = the full pipeline
   (Gilead, Teva, CSL, Merck KGaA and similar filterable trackers).
5. **SPA shell, data-only-after-JS, no embedded JSON** — the server-rendered
   HTML shows the filter chrome and may even render the first 10–20 rows of
   the default filter combination, but the bulk of the data lives in an
   XHR fetched by a JS bundle. Pfizer's `pfizer.com/science/drug-product-pipeline`
   is the textbook example (Drupal 10 + `pfizer_pipeline_immersive` widget:
   static HTML serves 10 / 96 rows, the rest mount after JS).

`src/pharmas/agent/pagination.py` exposes one helper per shape:

| Helper | Use when … |
|---|---|
| `fetch_all_pages(fetch_fn, *, url, page_param=...)` | URL pagination; `fetch_fn` is `requests`- or Playwright-shaped. |
| `loop_until_idle(page, *, item_selector, more_button_selector, ...)` | "Load more" / "Next" button. |
| `infinite_scroll(page, *, item_selector, ...)` | Records appear on scroll. |
| `exhaust_filters(page, *, filter_clicks, item_selector, dedup_key, ...)` | Filterable tracker — iterate cartesian product of filter groups. |
| `discover_spa_endpoints_html(html, base_url)` | Cheapest probe: static scan for hints (`data-src`, `drupalSettings`, `<link rel=preload as=fetch>`) to a JSON endpoint. |
| `discover_spa_endpoints_playwright(page, *, listen_seconds=8)` | Run inside a `scrape_pipeline.py`: open the widget in Playwright and capture every JSON response for N seconds — the network tab, automated. |
| `summarize(pages, *, dedup_key=...)` | Compute `PaginationSummary` → `raw_pipeline_meta.json`. |
| `detect_url_pagination(fetch_fn, *, url, max_probes=3)` | Cheap probe: does this URL have iterated `?page=N`? |

### When to use them

- **`agent.probe_webpage`** (in `src/pharmas/agent/probe.py`) auto-fills
  `has_pagination`, `pagination_mechanism`, `detected_total_pages`,
  `first_page_url`, `next_page_selector_hint`, `load_more_selector_hint`,
  plus `spa_signature`, `spa_candidate_endpoints`, `requires_interaction`.
  The SPA path is **multi-signal**: page-size `<select>`, multiple `<canvas>`,
  many `data-attr-filter=` markers, `data-product-count` mismatch vs the
  static row count, and Drupal-without-JSON:API hint at each other. Read
  these before deciding the scrape shape.
- **`agent.ingest_webpage`** (in `src/pharmas/agent/ingest.py`) does three
  things automatically:
  1. If `probe_results["webpage"]["requires_interaction"]` is `True` → SPA
     branch: cheap-try the static-scan candidate URLs; on miss, write a
     structured `raw_pipeline_meta.json` (`mechanism="spa"`, the SPA
     signature, the candidate endpoints, the next-action message) and
     return `[]`.
  2. URL pagination detected in the saved HTML → loop via
     `fetch_all_pages`. Override with `pagination={"skip_auto_loop": True}`.
  3. Static HTML or `__NEXT_DATA__` JSON parsed, otherwise a scrapling
     fallback runs.
- **For Tier 3 widgets** (`Load more`, infinite scroll, filter combinations,
  SPAs), any auto-detection in `ingest_webpage` is just a hint. The real
  extraction belongs in `src/pharmas/<company>/scrape_pipeline.py`, which
  should call the relevant helper instead of hand-rolling a loop. For SPAs,
  the rough pattern is:
    1. `discover_spa_endpoints_playwright` while the widget boots, to find
       the XHR that fetches the dataset.
    2. Either: hit that XHR directly with `requests` (skip the widget) for
       cleanly paginated APIs, or: drive the widget with `loop_until_idle`
       / `exhaust_filters` and read the rendered DOM, depending on whether
       the server endpoint is replayable.
- **`agent.finalize.write_log_md`** renders a `## 5. Pagination` section in
  the company's `log.md` whenever `has_pagination` or `requires_interaction`
  is `True`. For SPAs it adds the SPA signature + candidate endpoints +
  the next-action verbatim from the sidecar.

### Completion check

After scraping, the human cross-check must include:

- `PaginationSummary.total_items` matches any "Showing N of M" / "Total
  records: N" counter visible on the live page. If no such counter exists,
  rely on the user's manual copy/paste (see "Verification" below) — same as
  for any other extraction. If the page shows "122 programs" but
  `total_items == 119`, the scrape is **incomplete** — reopen and re-run
  rather than ship a partial dataset.
- `duplicate_count` should be `0` for URL-paginated sources. Non-zero means
  the dedup selector picked a non-unique key — fix the key, re-scrape.
- For SPA-detected sources, the sidecar's `next_action` MUST be acted on
  before the company is marked Done. A SPA extraction that only ships the
  rows visible in the static HTML is a partial extraction — don't accept it.

## Verification (every company)

Before calling it done:
- Row count and identity (name/area/phase) matches a manual read of the
  source, in the same order.
- A few sample rows' full text cross-checked against the live source/PDF.
- No unintended duplicate/degenerate values (e.g. `indication` accidentally
  equal to `asset_name` — happened once on Novo Nordisk from a source-side
  quirk, caught by comparing the two columns programmatically).
- **Ask the user to send a manual copy/paste of some or all of the source**
  (e.g. a table they copied straight off the live page) and diff it against
  the scraped/mapped output — don't rely solely on your own re-reading of the
  same source you scraped from, since a bug in your own selector logic
  reproduces the same blind spot every time you re-check it yourself. This is
  what caught MSD's two real bugs after the extraction was first reported
  done: 12/105 indications missing a region tag that lived in an element the
  scraper never selected, and one compound's name coming from a buggy source
  HTML attribute instead of its (correct) visible heading — neither was
  visible from re-reading the same raw HTML the scraper already read.
- **Report every inconsistency this turns up in both places**: the
  company's `log.md` (as a dated addendum if the company was already marked
  Done) and the GitHub issue (reopen it if already closed, comment with what
  was wrong and the fix, then close again) — don't just fix the code and move
  on, since these are exactly the kind of source-structure surprises the next
  company's extraction should be able to learn from.

## Git hygiene

- `.claude/` (skills), `.DS_Store`, and `*.egg-info/` are gitignored — don't
  commit them.
- Commit the source file(s) + `__init__.py` + converter + `log.md` + parquet
  together; mark the company `Done` in `docs/sources.md` with a link to its
  `log.md` (pointing at `src/pharmas/<company>/log.md`) in the same commit.
- Only commit/push when the user explicitly asks.
- Before pushing, `git fetch`/check for teammates' commits — this repo has
  more than one person extracting companies in parallel; a structural refactor
  landed mid-project once already (moving `pharmas/` -> `src/pharmas/`), so
  don't assume the layout in this file is still current without checking
  `docs/sources.md` and an existing company folder first.
