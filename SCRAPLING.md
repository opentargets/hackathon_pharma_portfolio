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

**Adopted practice — curl-first quality gate**: before writing a click-loop
Playwright script for the next Tier 3 site, `curl` the raw page first and check
for an embedded data blob (`__NEXT_DATA__`, `ld+json`, inline `<script>` JSON)
or an API endpoint the widget calls — if the data's already there, skip the
browser entirely. Borrowed from `yfe404/web-scraper`'s phased
curl-before-browser approach (see below) and added to
`.claude/skills/scrapling/SKILL.md`'s decision tree. Novo Nordisk's data genuinely
wasn't available until a button click fired an AJAX call, so this wouldn't have
changed that outcome, but it's a cheap check worth doing every time before
reaching for a full click-loop.

## Potential alternative: Firecrawl

[BexTuychiev/firecrawl-claude-code-skill](https://github.com/BexTuychiev/firecrawl-claude-code-skill)
wraps the [Firecrawl](https://firecrawl.dev) SaaS API instead — adds web search,
multi-page doc-site crawling, screenshots, and AI-schema-based structured
extraction (no manual CSS selectors), all things scrapling doesn't do. Reviewed,
code is clean (no vulnerabilities). Not installed: requires a `FIRECRAWL_API_KEY`
(paid third-party service, free tier 500 credits) and sends scraped page content
through Firecrawl's servers rather than staying local. Also its bundled script
doesn't expose Firecrawl's click/interact actions, so it wouldn't have solved the
Novo Nordisk click-to-reveal case any better than plain Playwright did. Worth
revisiting if a future source needs search/crawl/screenshot and an API key becomes
available.

## Considered and rejected: yfe404/web-scraper

[yfe404/web-scraper](https://github.com/yfe404/web-scraper) is a more elaborate
adaptive-reconnaissance skill (curl first, quality gates, self-critiquing
report, TypeScript/Apify Actor productionization). Reviewed, code itself is
clean, but not usable as installed: its browser/traffic-interception phases
(most of the skill) call tools like `proxy_start()` / `interceptor_chrome_*()` /
`humanizer_*()` from a separate "proxy-mcp" MCP server that isn't published
anywhere — its own docs cite the source as a local path
(`/home/yms/Documents/proxy-mcp/`) on the author's machine, not a repo or
package. Without that MCP server, only its Phase 0 (curl-based static
detection) actually runs. It's also entirely TypeScript/Apify-Cloud oriented
for implementation, which doesn't fit this repo's Python/uv setup. Not
installed; only its curl-first quality-gate idea (above) was worth keeping.
