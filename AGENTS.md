# AGENTS.md — Pharma Portfolio Mining

## Project structure

`src/`-layout Python package (setuptools, installed editable via `uv sync`). Each pharma company lives in `src/pharmas/<company>/` with:
- `<scrape|convert>_to_parquet.py` — entrypoint script
- `log.md` — mapping decisions, data-quality anomalies
- raw source file(s) + `<company>_pipeline.parquet`

Shared schema at `src/schema.py` (`PipelineRecord` + `Phase` enum). Import as `from schema import ...` — resolves via `src/` package-dir mapping, but only after `uv sync` installs the project editable.

`PipelineRecord.model_config = {"extra": "allow"}` — extra fields like `others` pass through without being declared on the model.

## Essential commands

| Action | Command |
|---|---|
| Install project | `uv sync` |
| Add dependency | `uv add <package>` |
| Run a converter | `uv run python src/pharmas/<company>/<script>.py` |
| Install browser binaries (Tier 3) | `uv run scrapling install` |
| Pagination helpers (Tier 3 widgets, URL/load-more/scroll/filter shapes) | `from pharmas.agent.pagination import fetch_all_pages, loop_until_idle, infinite_scroll, exhaust_filters, summarize` |
| SPA endpoint discovery (Pfizer-style JS-only widget) | `from pharmas.agent.pagination import discover_spa_endpoints_html, discover_spa_endpoints_playwright` |

## No tests, no CI, no linter/typecheck config

This repo has none. No pre-commit either. Don't look for them.

## Extraction workflow

`instruction_for_agent.md` is the authoritative workflow. Key rules:
- **One pharma at a time.** Finish the current one before starting the next.
- **Prefer structured sources.** CSV/xlsx/PDF table before scraping.
- **Check both the downloadable file AND the live webpage** before deciding — tier labels in `docs/sources.md` can be stale.
- **Pagination.** Pipeline pages distribute records across more than one fetchable unit (URL `?page=N`, "Load more", infinite scroll, filter combinations, **SPA shell with data-only-after-JS**). `agent.pagination` exposes one helper per shape — use them, don't hand-roll loops. For SPAs, `discover_spa_endpoints_*` finds the XHR and `ingest_webpage` writes a structured stop-and-report sidecar.
- **Two-pass for Tier 3 (JS widgets):** scrape raw data first (`scrape_pipeline.py` + `raw_pipeline.json`), then map to schema in a separate script.
- **curl before browser** on every Tier 3 source — check for embedded JSON blobs (`__NEXT_DATA__`, `ld+json`, inline `<script>` JSON) or an API endpoint before writing a click-loop Playwright script.
- **Before writing the converter**, confirm field-mapping decisions with the user (batch up to 4 questions at once).
- **User must cross-check output** against a manual copy/paste of the source before marking Done.

## Git

- Never commit `.claude/`, `.DS_Store`, `*.egg-info/` (gitignored).
- Commit source files + `__init__.py` + converter + `log.md` + parquet together.
- Update `docs/sources.md` status + link to `log.md` in the same commit.
- Only commit/push when asked.
- Before pushing, `git fetch` — teammates may have restructured.

## Scraping skill

`.claude/skills/scrapling/` tracks the scraping skill in git (no per-person install). The skill's quick paths handle static/Cloudflare pages only. Click-to-reveal JS widgets need a custom Playwright script (browser binaries are already installed via `uv run scrapling install`).
