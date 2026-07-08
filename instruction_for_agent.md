# Instructions for the extraction agent

Distilled from three completed extractions: Roche (Tier 1, clean CSV), GSK
(Tier 2, xlsx), Novo Nordisk (Tier 3, JS widget, scraped). Follow this workflow
for every remaining company in `docs/sources.md`.

## Ground rules (from `context.md`)

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

1. Locate/confirm the source file (ask the user if it's not already in the
   folder). If both a table and a PDF/chart exist, sanity-check they roughly
   agree before trusting the table.
2. Inspect the data: unique values per column, sample rows, obvious anomalies
   (transposed columns, ID collisions, duplicate headings, missing
   indication/MoA columns).
3. **Before writing the converter**, confirm field-mapping decisions with the
   user via targeted questions (batch up to 4 at once), informed by the actual
   data — never guess silently. Ambiguities that come up every time:
   - `asset_name`: which column is the real identifier (internal compound
     code vs. generic/trade name)? Collisions across rows are possible — ask
     whether to accept them or need a fallback.
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

## Verification (every company)

Before calling it done:
- Row count and identity (name/area/phase) matches a manual read of the
  source, in the same order.
- A few sample rows' full text cross-checked against the live source/PDF.
- No unintended duplicate/degenerate values (e.g. `indication` accidentally
  equal to `asset_name` — happened once on Novo Nordisk from a source-side
  quirk, caught by comparing the two columns programmatically).

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
