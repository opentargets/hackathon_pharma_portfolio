# Novo Nordisk extraction log

Source: https://www.novonordisk.com/science-and-technology/r-d-pipeline.html
(Tier 3: JS-widget, no static table/PDF/CSV.)

## 1. Scraping tool setup

No scraping capability was available in the environment. Installed:
- `scrapling[fetchers]` via `uv add` (added to project `pyproject.toml`/`uv.lock`)
- `uv run scrapling install` (Playwright/Camoufox browser binaries)
- Claude Code skill from https://github.com/Cedriccmh/claude-code-skill-scrapling,
  copied into `.claude/skills/scrapling/` (project-level).

Note: pre-existing saved HTML files in `pharmas/novonordisk/` (`R&D pipeline.html` +
`_files/`) disappeared from disk between the start of this session and when we went
to inspect them (not in Trash, not Spotlight-indexed) — unrelated to any action taken
here. Not used; scraped live instead since the saved static HTML wouldn't contain the
AJAX-loaded dialog content anyway.

## 2. Page structure

The pipeline is a grid: 3 therapeutic areas (`diabetes`, `obesity`,
`rare-blood-disorders`) x 4 phase columns (`phase-1`, `phase-2`, `phase-3`, `filed`).
Each drug is a `div.area-item` (role=button). Clicking one fires an AJAX request to
`/bin/nncorp/rnd-pipeline?pressSearch=...&companySearch=...` and fills a
`.rnddialog-wrapper` modal with a description paragraph (indication in bold + free-text
description) plus "Company Announcements" / "Press Releases" dropdowns (generic
keyword-matched news search results, not curated per-drug fields — not scraped, would
just be noisy/time-varying).

A `onetrust` cookie-consent overlay blocks clicks until dismissed (handled by clicking
the "Accept" button first).

## 3. Scraping approach

`pharmas/novonordisk/scrape_pipeline.py` — plain Playwright (via scrapling's installed
browser deps), headless Chromium:
1. Load page, dismiss cookie banner.
2. Enumerate all `.area-item` buttons (37 total).
3. For each: read name from `aria-label`, area+phase from ancestor
   `.rndarea-wrapper` class, click it, wait for dialog, extract description
   text/html from `.dialog-content .paragraph-l`, close dialog, next.

## 4. Output

Raw row-level data only, per instructions — no schema mapping yet:
- `pharmas/novonordisk/raw_pipeline.json` (name, area, phase, description_text,
  description_html)
- `pharmas/novonordisk/raw_pipeline.csv` (name, area, phase, description_text)

37 rows: 5 in diabetes/phase-1, 5 in obesity/phase-1, 1 in rare-blood-disorders/phase-1,
5 in diabetes/phase-2, 4 in obesity/phase-2, 3 in rare-blood-disorders/phase-2,
5 in diabetes/phase-3, 3 in obesity/phase-3, 1 in rare-blood-disorders/phase-3,
2 in diabetes/filed, 2 in obesity/filed, 1 in rare-blood-disorders/filed.

## 5. Schema mapping (`novonordisk_to_parquet.py`)

Confirmed interactively, decisions:

- `phase`: `phase-1/2/3` -> `Phase 1/2/3` directly; `filed` -> `Preregistration`
  (submitted, not yet approved — same resolution as GSK's `Registration`).
- `therapeutic_area`: source's CSS slug (`diabetes`/`obesity`/`rare-blood-disorders`)
  title-cased to match the page's own visible label (`Diabetes`/`Obesity`/
  `Rare Blood Disorders`), not stored as the raw slug.
- `indication` / `mechanism_of_action` split from `description_text`, which has no
  dedicated column (unlike GSK's MoA column, unlike Roche's separate Indication
  column): most rows are `"Indication heading\nMoA/detail sentence"` -> first line
  is indication, rest is MoA. 3 rows (UBT251, Triple/obesity, Cagrilintide) are a
  single sentence with no heading — indication is pulled from a `"for (the)
  treatment of X"` clause via regex if present (works for 2 of 3), else falls back
  to the therapeutic area label (Cagrilintide, which has no such clause at all).
- **Data-quality anomaly found and flagged** (same category as Roche/GSK's
  transposed-column issues): 2 rows have the dialog's heading line equal to the
  *asset name itself* rather than a disease (`siRNA GalXC-GYS2`, `Subcutaneous
  Zenagamtide`/diabetes) — apparently no indication text was authored for these on
  the source page. Resolved (user confirmed): fall back to the therapeutic area
  label for these 2, same rule as the no-heading single-sentence rows, rather than
  parsing the disease name out of the MoA sentence.
- `asset_name` = `name` verbatim (no internal compound code on this page, unlike
  Roche's RG-codes).
- `others` = `["Raw description: <full description_text>"]` on every row, so the
  original unsplit text is preserved for audit even though indication/MoA were
  heuristically split.
- `synonyms`, `trial_id`, `notes` = null (not exposed by this source).

Output: `pharmas/novonordisk/novonordisk_pipeline.parquet` (37 rows).
