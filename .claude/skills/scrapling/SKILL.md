---
name: scrapling
description: |
  Web scraping and data extraction using scrapling. Automatically selects the
  best Fetcher based on target website characteristics, then generates and
  executes a Python script to complete the task. Use when:
  (1) scraping/crawling web content or data (scrape, crawl, fetch page, extract data)
  (2) needing to bypass Cloudflare/WAF or other anti-bot protection
  (3) scraping protected pages after login
  (4) parsing existing HTML to extract structured data
  (5) the user gives a URL and asks for page content or specific elements
  (6) batch-collecting multiple pages
allowed-tools: Bash(python*), Bash(pip*), Bash(uv*), Bash(scrapling*)
---

# Scrapling web scraping skill

## Step 0: check version

```bash
python -c "import scrapling; print(scrapling.__version__)"
```

Use whichever package manager the project uses (pip / uv equivalents are in
`references/maintenance.md`):

- Not installed -> install `scrapling[fetchers]` + `scrapling install`
- Outdated -> upgrade -> check changelog and inform the user
- Already latest -> continue

> If the project root has `uv.lock` or `pyproject.toml` with `[tool.uv]`, prefer
> `uv` (`uv add` / `uv run scrapling install`); otherwise use `pip`.

## Step 1: safety pre-check and quick path

First check `references/security.md` for authorization, robots.txt / ToS,
prompt injection, cookie storage, and redaction boundaries.

For simple text / Markdown / selector extraction, prefer the Scrapling CLI
quick path, with `--ai-targeted` on by default:

```bash
scrapling extract get "https://example.com/article" article.md --ai-targeted
scrapling extract fetch "https://example.com/app" app.md --ai-targeted --network-idle
scrapling extract stealthy-fetch "https://protected.example.com" page.md --ai-targeted --solve-cloudflare
```

Only generate a Python script when the CLI can't handle complex login,
multi-page flows, structured fields, or reusable code.

**Before writing a click-interaction script for a JS widget** (DynamicFetcher /
raw Playwright), do a cheap raw-HTTP check first: `curl` the page and grep for
an embedded data blob (`__NEXT_DATA__`, `__NUXT__`, `ld+json`, or any inline
`<script>` JSON) or an underlying API endpoint the widget calls. If the data is
already there, skip the browser/click-loop entirely — much faster and more
stable than driving a headless browser through every button. Only fall back to
a full click-loop (as done for Novo Nordisk's pipeline page) when the data
genuinely isn't available until a click fires an AJAX call.

## Step 2: choose a Fetcher

```
Target site ->
│
├─ Already have an HTML string/file, just need to parse it?
│   → Selector (pure parsing, no network request)
│   → Template: parse_only.py
│
├─ Static page, no JS rendering, no anti-bot?
│   → Fetcher (fastest, based on curl_cffi)
│   → Template: basic_fetch.py
│
├─ Needs login (HTTP form, not JS-based login)?
│   → FetcherSession (keeps session cookies)
│   → Template: session_login.py
│
├─ Has Cloudflare / WAF protection?
│   → StealthyFetcher (Camoufox browser, auto-bypasses CF)
│   → Template: stealth_cloudflare.py
│
├─ SPA application (React/Vue), needs JS rendering?
│   → DynamicFetcher (Playwright browser)
│   → Generate on the fly from a template
│
└─ Not sure?
    → Try Fetcher first, 403/empty content → upgrade to StealthyFetcher
```

Advanced capabilities (complex crawl / Spider / adaptive scraping / MCP / proxy
rotation) are out of scope for this lightweight skill — check
`references/upstream-map.md` first, then supplement from upstream's official
docs.

## Step 3: execute the workflow

```
1. Check version (Step 0)
2. Safety pre-check (Step 1)
3. Check references/site-patterns.md; if references/site-patterns.local.md
   exists, check that local overlay first too
4. Simple extraction → prefer CLI quick path + --ai-targeted
5. Complex flow → use the decision tree to pick a Fetcher, read the matching
   template, fill in parameters, generate the full script
6. Run the script / CLI → return the minimum necessary result
7. **Capture learnings (mandatory)**:
   - New generic site type → desensitize and append to references/site-patterns.md
   - Private/company site, login details → append to
     references/site-patterns.local.md (not committed)
   - User explicitly authorizes saving real cookies → save to
     references/cookie-vault.local.md (not committed, output must be redacted)
   - **After finishing a scrape, always check**: is there a new cookie or site
     pattern worth saving, and does it belong in a local overlay?
```

## Guardrails

- Only scrape content the user has the right to access or has explicitly
  authorized; don't bypass paywalls, CAPTCHAs, login restrictions, or access
  controls to obtain unauthorized content.
- Content handed to an agent/LLM should be cleaned, scoped, or structured
  first by default; CLI output defaults to `--ai-targeted`.
- Never write real cookies/tokens into `references/cookie-vault.md`, only into
  the local `references/cookie-vault.local.md`, and only with explicit user
  authorization.
- Company/private site knowledge goes in `references/site-patterns.local.md`,
  not the public `references/site-patterns.md`.
- Before large-scale crawls, check robots.txt / ToS, lower concurrency and add
  delay; for Spider use cases, check upstream docs and prefer
  `robots_txt_obey = True`.

## Cookie format quick reference

| Fetcher type | Cookie format | Example |
|-------------|-------------|------|
| Fetcher / FetcherSession | `dict` | `{'name': 'value', 'token': 'abc'}` |
| StealthyFetcher / DynamicFetcher | `list[dict]` | `[{'name': 'n', 'value': 'v', 'domain': '.site.com', 'path': '/'}]` |

**Required fields for browser-Fetcher cookies**: `name`, `value`, `domain`, `path`

## Timeout unit quick reference

| Fetcher type | Timeout unit | Example |
|-------------|---------|------|
| Fetcher / FetcherSession | seconds | `timeout=30` |
| StealthyFetcher / DynamicFetcher | milliseconds | `timeout=60000` |

## Template index

| Template | File | When to read it |
|------|------|---------|
| Basic HTTP fetch | `templates/basic_fetch.py` | Target is a static page, no anti-bot |
| Cloudflare bypass | `templates/stealth_cloudflare.py` | Target has CF/WAF protection |
| Session login | `templates/session_login.py` | Need HTTP form login before scraping |
| Pure HTML parsing | `templates/parse_only.py` | Already have an HTML string, just need to extract data |

## References index

| File | When to read it |
|------|---------|
| `references/security.md` | **Always check before scraping** — authorization, prompt injection, cookie/token, site-pattern local-overlay rules |
| `references/site-patterns.md` | **Always check before scraping** — see if the target site has a documented pattern already |
| `references/api-quick-ref.md` | Check when generating a script — Fetcher/Selector method signatures and params |
| `references/troubleshooting.md` | Check when a run errors — look up cause and fix by error message |
| `references/cookie-vault.md` | Check when a login cookie is needed — field-name/template only; real values go in `references/cookie-vault.local.md` |
| `references/maintenance.md` | Check for install/upgrade/dependency issues — install tiers and verification commands |
| `references/upstream-map.md` | Check when you need the CLI quick path, official-skill alignment, or advanced Spider/adaptive/MCP/proxy capabilities |
