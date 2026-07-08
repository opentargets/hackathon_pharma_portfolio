# Scrapling skill (Tier 3 sources)

Used for pharma pipeline pages with no static CSV/PDF (Tier 3: J&J, Eli Lilly,
Sanofi, Novo Nordisk, Gilead, Teva, CSL, Merck KGaA — see `docs/sources.md`).

## What it is

- Library: [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) — Python
  scraping lib with auto Fetcher selection (static/Cloudflare/JS-rendered).
- Skill: [Cedriccmh/claude-code-skill-scrapling](https://github.com/Cedriccmh/claude-code-skill-scrapling)
  — Claude Code skill wrapping it (decision tree for which Fetcher to use, CLI
  quick paths, templates).

## Install (already done in this repo)

```bash
# 1. library, into project uv env
uv add "scrapling[fetchers]"
uv run scrapling install   # Playwright/Camoufox browser binaries

# 2. skill, project-level
git clone https://github.com/Cedriccmh/claude-code-skill-scrapling.git /tmp/scrapling-skill
cp -r /tmp/scrapling-skill /Users/yt4/Projects/hackathon_pharma_portfolio/.claude/skills/scrapling
rm -rf /Users/yt4/Projects/hackathon_pharma_portfolio/.claude/skills/scrapling/.git
```

Both now live in this repo (`.claude/skills/scrapling/`, `pyproject.toml`/`uv.lock`)
— no reinstall needed for the next Tier 3 pharma.

## Verdict: mixed

**Good for:**
- Static pages, Cloudflare/WAF-protected pages — Fetcher/StealthyFetcher
  auto-selection works well.
- Quick one-shot CLI extraction (`scrapling extract get ... --ai-targeted`) for
  simple text/markdown grabs.

**Not useful for:**
- Click-to-reveal JS widgets (Novo Nordisk's pipeline page: click a drug button ->
  AJAX call -> modal fills with description). None of the skill's quick paths
  (Fetcher/StealthyFetcher/DynamicFetcher CLI) handle multi-step interaction like
  this — had to drop to raw Playwright (a scrapling dependency, so already
  installed) and hand-write the click-loop script (`pharmas/novonordisk/scrape_pipeline.py`).

Expect the same for other Tier 3 pharmas with interactive widgets: the skill's
value is mainly "scrapling gets Playwright + browser binaries installed for free"
— the actual interaction logic still needs a custom script per site.
