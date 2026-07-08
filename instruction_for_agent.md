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

## Per-company folder layout

Everything for a company lives in `pharmas/<company>/`:

- the raw source file(s) (CSV/xlsx/PDF, or a scrape script + raw JSON/CSV dump
  for Tier 3)
- `schema.py` — copy-paste of the shared `PipelineRecord` model + `Phase` enum
  from a prior company's folder (identical every time; kept per-folder rather
  than centralized, by explicit user preference — no top-level `scripts/` dir)
- `<company>_to_parquet.py` (or `<company>_csv_to_parquet.py` /
  `<company>_xlsx_to_parquet.py`) — the converter
- `log.md` — extraction + mapping decision log (see below)
- the resulting `<company>_pipeline.parquet`

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
     both are explicitly allowed extras per `docs/data-model.md`.
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
   it, don't reinstall. In practice, click-to-reveal widgets need raw
   Playwright (a scrapling dependency) rather than scrapling's own quick-path
   Fetchers, which only handle static/Cloudflare-protected pages. Expect a
   cookie-consent overlay to block clicks until dismissed first.
   - Write `pharmas/<company>/scrape_pipeline.py`, dump every row's fields as
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

- `.claude/` (skills) and `.DS_Store` are gitignored — don't commit them.
- Commit the source file(s) + `schema.py` + converter + `log.md` + parquet
  together; mark the company `Done` in `docs/sources.md` with a link to its
  `log.md` in the same commit.
- Only commit/push when the user explicitly asks.
