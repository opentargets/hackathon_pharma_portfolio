"""Generalizable pagination helpers for pipeline-page scraping.

Used by:
  - src/pharmas/agent/probe.py  (cheap detection of which mechanism applies)
  - src/pharmas/agent/ingest.py (auto-loop inside ingest_webpage for Tier 1/2
    sites that turn out to be server-paginated)
  - per-company src/pharmas/<company>/scrape_pipeline.py  (for Tier 3 widgets
    that have click-to-reveal or filterable UIs)

Five real-world pagination shapes are supported:
  1. URL pagination       -> fetch_all_pages  (e.g. novartis.com/research-development/novartis-pipeline)
  2. "Load more" button   -> loop_until_idle  (re-clicks until count stops growing)
  3. Infinite scroll      -> infinite_scroll  (scroll to bottom, repeat)
  4. Filter combinations  -> exhaust_filters  (Gilead / Teva / CSL / Merck KGaA)
  5. SPA shell, data-only-after-JS -> discover_spa_endpoints_html / _playwright
     (Pfizer's immersive widget; the XHR for the data lives inside a JS bundle
     and isn't visible in the initial HTML.)

Plus `summarize()` -> `raw_pipeline_meta.json`, so the human cross-check step
can verify "we visited N pages and got M unique items, not M+1 (which would
indicate duplicates leaking)".

Reference usage (copy-paste these snippets into a new scrape_pipeline.py):

    # 1) URL pagination -- e.g. Novartis
    from agent.pagination import fetch_all_pages, summarize
    import requests
    pages = fetch_all_pages(
        lambda url: requests.get(url, timeout=30, headers=UA).text,
        url="https://example.com/pipeline",
        page_param="page",
        dedup_key=lambda html: re.findall(r"<li[^>]*>(.*?)</li>", html, re.S),
    )
    summary = summarize(pages)

    # 2) "Load more" button
    from agent.pagination import loop_until_idle, summarize
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        page.goto(URL, wait_until="networkidle")
        items = loop_until_idle(
            page, item_selector=".pipeline-row", more_button_selector="button.load-more",
        )

    # 3) Infinite scroll
    from agent.pagination import infinite_scroll
    items = infinite_scroll(page, item_selector=".pipeline-row")

    # 4) Filter combinations (e.g. Gilead)
    from agent.pagination import exhaust_filters
    out = exhaust_filters(
        page,
        filter_clicks=[
            [("input[aria-label='Phase 1']", "p1"), ("input[aria-label='Phase 2']", "p2")],
            [("input[aria-label='Phase 3']", "p3")],
        ],
        item_selector=".pipeline-card",
        dedup_key=lambda html: re.search(r"data-id=\"(\\d+)\"", html).group(1),
    )

    # 5) SPA discovery (Pfizer-style)
    from agent.pagination import (discover_spa_endpoints_html,
                                    discover_spa_endpoints_playwright)
    static_candidates = discover_spa_endpoints_html(html_body, base_url)
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        ep = discover_spa_endpoints_playwright(page, listen_seconds=8)
    # Then drive the widget: ep[0].url is the most likely data endpoint; hit it
    # directly with requests, or use loop_until_idle/exhaust_filters against the
    # rendered DOM.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# ----- public types ----------------------------------------------------------

@dataclass
class PaginationSummary:
    mechanism: str  # "url" | "load_more" | "infinite_scroll" | "filters" | "none"
    page_count: int = 0
    total_items: int = 0
    duplicate_count: int = 0
    sample_url_per_page: list[str] = field(default_factory=list)
    stopped_reason: str = "single_page"  # "exhausted" | "max_pages" | "idle" | "duplicates" | "single_page" | "filters"

    def to_meta_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpaEndpoint:
    url: str
    method: str  # "GET" | "POST"
    content_type: str
    body_size: int
    first_seen_at: float
    sample: str  # first ~200 chars of the response body

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----- internal helpers ------------------------------------------------------

_IDLE_SENTINELS = (
    "no results",
    "no programs",
    "no molecules",
    "no assets",
    "0 results",
    "0 programs",
    "nothing to show",
    "nothing found",
    "end of results",
)

_PAGE_PARAM_CANDIDATES = ("page", "p", "pg", "offset", "start", "skip")


def _set_query(url: str, **params: str | int) -> str:
    scheme, netloc, path, qs, frag = urlsplit(url)
    existing = dict(parse_qsl(qs, keep_blank_values=True))
    for k, v in params.items():
        existing[k] = str(v)
    return urlunsplit((scheme, netloc, path, urlencode(existing), frag))


def _body_signature(html: str) -> str:
    """Cheap, selector-agnostic fingerprint for "did this page look the same
    as the previous one?". Strips whitespace + tags and lengthens the prefix."""
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text[:512]


def _looks_idle(html: str) -> bool:
    body = html.lower()
    return any(s in body for s in _IDLE_SENTINELS)


# ----- 1) URL pagination -----------------------------------------------------

def fetch_all_pages(
    fetch_fn: Callable[[str], str],
    *,
    url: str,
    page_param: str = "page",
    total_pages: int | None = None,
    max_pages: int = 200,
    dedup_key: Callable[[str], Iterable[str]] | None = None,
    idle_sentinel: Callable[[str], bool] | None = None,
    sleep_ms: int = 200,
) -> list[tuple[int, str]]:
    """Iterate URL-paginated pages until exhausted.

    `fetch_fn` is a callable that takes a URL and returns the response body as
    a string. This indirection lets callers pass either `requests`, `Fetcher`,
    `StealthyFetcher`, or a Playwright lambda -- the helper itself never
    imports any of them.

    Stops on (in order): `total_pages` reached; the body matches the previous
    page's signature; `idle_sentinel(html)` is true; dedup_key detects an
    item already seen; or `max_pages` safety rail.

    Returns `[(page_index, html), ...]`. page_index == 0 is the first page.
    """
    pages: list[tuple[int, str]] = []
    seen_signatures: set[str] = set()
    seen_items: set[str] = set()
    idle_check = idle_sentinel or _looks_idle

    for page_index in range(max_pages):
        if page_index == 0:
            this_url = url
        else:
            this_url = _set_query(url, **{page_param: page_index})

        body = fetch_fn(this_url)
        pages.append((page_index, body))

        sig = _body_signature(body)
        if page_index > 0 and sig in seen_signatures:
            pages.pop()
            break
        seen_signatures.add(sig)

        if idle_check(body):
            break

        if dedup_key is not None:
            try:
                items_this_page = list(dedup_key(body))
            except Exception:
                items_this_page = []
            if items_this_page and all(i in seen_items for i in items_this_page):
                break
            for i in items_this_page:
                seen_items.add(i)

        if total_pages is not None and (page_index + 1) >= total_pages:
            break

        if sleep_ms:
            time.sleep(sleep_ms / 1000.0)

    return pages


def detect_url_pagination(
    fetch_fn: Callable[[str], str],
    *,
    url: str,
    max_probes: int = 3,
) -> dict[str, Any]:
    """Cheap probe: does this URL have an iterated `?page=N` (or similar) and
    how many pages does it have? Capped at `max_probes` extra requests."""
    result = {"has_pagination": False, "page_param": None,
              "detected_total_pages": None, "page_urls": []}
    for param in _PAGE_PARAM_CANDIDATES:
        pages: list[tuple[int, str]] = []
        prev_sig = None
        for page_index in range(1, max_probes + 1):
            this_url = _set_query(url, **{param: page_index})
            try:
                body = fetch_fn(this_url)
            except Exception:
                break
            sig = _body_signature(body)
            if sig == prev_sig:
                break
            prev_sig = sig
            pages.append((page_index, body))
            if _looks_idle(body):
                break
        if pages and len(pages) >= 1:
            result.update({
                "has_pagination": True,
                "page_param": param,
                "detected_total_pages": len(pages) + 1,  # +1 for page_index=0 default
                "page_urls": [url] + [_set_query(url, **{param: p}) for p, _ in pages],
            })
            return result
    return result


# ----- 2) Load-more -----------------------------------------------------------

def loop_until_idle(
    page: Any,
    *,
    item_selector: str,
    more_button_selector: str,
    max_iter: int = 50,
    wait_ms: int = 700,
    dedup_key: Callable[[str], str] | None = None,
) -> list[str]:
    """Click a 'Load more' / 'Show more' / 'Next page' button until the
    item count stops growing. Returns the per-item HTML snippets.

    `page` is a Playwright Page (sync or async). Mirrors the click-loop
    pattern already used by novonordisk/scrape_pipeline.py and
    sanofi/scrape_pipeline.py -- same behaviour, generalised.
    """
    snippets: list[str] = []
    seen_keys: set[str] = set()
    prev_count = -1
    for it in range(max_iter):
        # capture currently-rendered items
        locs = page.locator(item_selector)
        try:
            count_now = locs.count()
        except Exception:
            count_now = 0

        for i in range(count_now):
            try:
                html = locs.nth(i).evaluate("el => el.outerHTML")
            except Exception:
                continue
            key = dedup_key(html) if dedup_key else None
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            snippets.append(html)

        if count_now == prev_count:
            break
        prev_count = count_now

        btn = page.locator(more_button_selector).first
        try:
            if not btn.is_visible():
                break
            btn.click(timeout=3000)
        except Exception:
            break

        try:
            page.wait_for_timeout(wait_ms)
        except Exception:
            break

        # more HTML may have rendered above existing items on some sites; the
        # next loop iteration captures them.
    return snippets


# ----- 3) Infinite scroll ----------------------------------------------------

def infinite_scroll(
    page: Any,
    *,
    item_selector: str,
    max_iter: int = 50,
    scroll_pause_ms: int = 700,
    scroll_step_px: int = 2000,
    dedup_key: Callable[[str], str] | None = None,
) -> list[str]:
    """Scroll the page to bottom in `scroll_step_px` increments until no new
    items mount. Returns per-item HTML snippets (deduped)."""
    snippets: list[str] = []
    seen_keys: set[str] = set()
    prev_count = -1
    for _ in range(max_iter):
        locs = page.locator(item_selector)
        try:
            count_now = locs.count()
        except Exception:
            count_now = 0

        if count_now == prev_count:
            break
        prev_count = count_now

        for i in range(count_now):
            try:
                html = locs.nth(i).evaluate("el => el.outerHTML")
            except Exception:
                continue
            key = dedup_key(html) if dedup_key else None
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            snippets.append(html)

        try:
            page.evaluate(f"window.scrollBy(0, {scroll_step_px})")
            page.wait_for_timeout(scroll_pause_ms)
        except Exception:
            break
    return snippets


# ----- 4) Filter combinations ------------------------------------------------

def exhaust_filters(
    page: Any,
    *,
    filter_clicks: list[list[tuple[str, str]]],
    item_selector: str,
    dedup_key: Callable[[str], str],
    post_apply_wait_ms: int = 1500,
    max_combinations: int = 64,
) -> dict[str, list[str]]:
    """Apply every combination of filter clicks, capture items per combo,
    dedup across combos by `dedup_key`. Used by Gilead/Teva/CSL/Merck KGaA.

    `filter_clicks` is a list of "groups" of `(selector, label)` pairs.
    Each group is treated as a multi-select (all labels checked together).
    Group outer list is treated as mutually exclusive (we iterate the cartesian
    product of group-choices). Example for Gilead's TA + Phase matrix:

        filter_clicks=[
            [("input[aria-label='Oncology']", "onc"),
             ("input[aria-label='Inflammation']", "infl"),
             ("input[aria-label='Virology']", "vir")],
            [("input[aria-label='Phase 1']", "p1"),
             ("input[aria-label='Phase 2']", "p2"),
             ("input[aria-label='Phase 3']", "p3")],
        ]

    Refuses to run if cartesian-product size > `max_combinations` and emits
    a print warning rather than silently truncating.
    """
    import itertools

    cart_size = 1
    for g in filter_clicks:
        cart_size *= max(len(g), 1)
    if cart_size > max_combinations:
        print(
            f"[pagination.exhaust_filters] refusing: cartesian size "
            f"{cart_size} exceeds max_combinations={max_combinations}"
        )
        return {}

    per_combo: dict[str, list[str]] = {}
    seen_keys: set[str] = set()

    def clear_all():
        # Best-effort: uncheck any checked filter inputs before applying a
        # new combination. Site-specific clearing belongs in the caller; this
        # is the default of clicking a generic 'Clear all' button if present.
        for sel in ["button:has-text('Clear')", "button:has-text('Reset')",
                     "a:has-text('Clear all')", "[aria-label='Clear']"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=300):
                    btn.click(timeout=2000)
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    for combo in itertools.product(*filter_clicks):
        label = "|".join(lbl for _, lbl in combo)
        clear_all()
        for sel, _ in combo:
            try:
                page.locator(sel).first.click(timeout=3000)
            except Exception:
                continue
        try:
            page.wait_for_timeout(post_apply_wait_ms)
        except Exception:
            pass

        locs = page.locator(item_selector)
        try:
            count = locs.count()
        except Exception:
            count = 0

        combo_snippets: list[str] = []
        for i in range(count):
            try:
                html = locs.nth(i).evaluate("el => el.outerHTML")
            except Exception:
                continue
            key = dedup_key(html)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            combo_snippets.append(html)

        per_combo[label] = combo_snippets

    return per_combo


# ----- 5) SPA endpoint discovery ---------------------------------------------

# Patterns for the static scan. URLs we already discount as not useful.
_NON_DATA_HINTS = (
    "google-analytics", "googletagmanager", "doubleclick", "facebook.com/tr",
    "adobedtm.com", "hotjar", "segment.io", "newrelic",
    ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".woff", ".woff2",
    ".ico", ".gif", ".otf", ".ttf", ".eot",
)

# Common SPA-data URL suffixes that we probe in HEAD as a fallback when the
# static scan finds nothing. Cheap (HEAD, 5s timeout) and only used by callers
# that explicitly opt in via `_probe_jsonapi_paths=True`.
_JSONAPI_PATH_CANDIDATES = (
    "/jsonapi",
    "/jsonapi/node/pipeline",
    "/api/pipeline",
    "/api/products",
    "/api/v1/pipeline",
    "/api/v1/products",
    "/node/pipeline?_format=json",
    "/rest/views/pipeline",
    "/pipeline?_format=json",
    "/pipeline.json",
    "/data/pipeline.json",
    "/pipeline-data.json",
)


def _looks_data_url(url: str) -> bool:
    lowered = url.lower()
    return not any(s in lowered for s in _NON_DATA_HINTS)


def discover_spa_endpoints_html(html: str, base_url: str
                                 ) -> list[SpaEndpoint]:
    """Cheap static scan of the initial HTML for hints to JSON endpoints.

    Looks for: `<link rel=preload as=fetch href=...>`, `data-src=`,
    `data-endpoint=`, `<script type=application/json>` blobs that mention URLs,
    and inline references to Drupal settings JSON paths.

    Returns `SpaEndpoint` candidates with body_size=0 (no network was made;
    callers can choose which ones to probe themselves). Mirrors the spirit of
    `instruction_for_agent.md`'s "open the network tab" rule, but offline.
    """
    endpoints: dict[str, SpaEndpoint] = {}
    from urllib.parse import urljoin as _uj
    now = time.time()

    def _add(url: str, method: str = "GET", content_type: str = "",
             sample: str = ""):
        if not url or url.startswith(("javascript:", "#", "data:")):
            return
        abs_url = _uj(base_url, url)
        if not _looks_data_url(abs_url):
            return
        if abs_url in endpoints:
            return
        endpoints[abs_url] = SpaEndpoint(
            url=abs_url, method=method, content_type=content_type,
            body_size=0, first_seen_at=now,
            sample=sample[:200] if sample else "",
        )

    # <link rel="preload" as="fetch" href="..."> and as="image" excluded.
    for m in re.finditer(
        r'<link[^>]+(?:rel|as)=["\']([^"\']*)["\'][^>]*href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    ):
        rel, href = m.group(1).lower(), m.group(2)
        if "fetch" in rel or "preload" in rel:
            _add(href)

    # data-src / data-endpoint / data-url / data-api
    for m in re.finditer(
        r'data-(?:src|endpoint|url|api|fetch-url|json-url)=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    ):
        _add(m.group(1))

    # <script type="application/json"> blobs - if they reference a URL on a
    # known data path, surface it.
    for m in re.finditer(
        r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        body = m.group(1)
        if not body:
            continue
        # Look for "url": "..." or path:"..."
        for url_m in re.finditer(
            r'["\']?(?:url|path|href|api|endpoint)["\']?\s*:\s*["\']([^"\']+)["\']',
            body,
        ):
            _add(url_m.group(1))

    # Drupal settings shape: drupalSettings.path or paths with /jsonapi etc.
    for m in re.finditer(
        r"[\"'](/[^\"']*(?:jsonapi|views/api|node/\w+\?_format=json|pipeline(?:\.json)?)[\"']?/[^\"']*)[\"']",
        html,
    ):
        _add(m.group(1))

    return list(endpoints.values())


def discover_spa_endpoints_playwright(
    page: Any,
    *,
    listen_seconds: int = 8,
    request_body_size: int = 0,
) -> list[SpaEndpoint]:
    """Open the page in Playwright and capture every JSON response for
    `listen_seconds`. Returns the unique URLs, sorted by body size descending.

    Mirrors the manual network-tab step from `instruction_for_agent.md` --
    just automated. Caller is responsible for `page.goto()` BEFORE calling
    this; this function only attaches the response listener and waits.
    """
    captured: dict[str, SpaEndpoint] = {}
    start = time.time()

    def _on_response(resp):
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            status = resp.status
            url = resp.url
        except Exception:
            return
        if status != 200:
            return
        if "json" not in ct and "json" not in url.lower() and "/api/" not in url.lower():
            return
        if url in captured:
            return
        try:
            body = resp.body()
        except Exception:
            body = b""
        try:
            text = body.decode("utf-8", errors="ignore") if body else ""
        except Exception:
            text = ""
        captured[url] = SpaEndpoint(
            url=url,
            method=resp.request.method if hasattr(resp, "request") else "GET",
            content_type=ct,
            body_size=len(body) if body else len(text),
            first_seen_at=time.time() - start,
            sample=text[:200],
        )

    page.on("response", _on_response)
    try:
        page.wait_for_timeout(int(listen_seconds * 1000))
    except Exception:
        pass
    try:
        page.remove_listener("response", _on_response)
    except Exception:
        pass

    return sorted(captured.values(), key=lambda e: -e.body_size)


# ----- summary ---------------------------------------------------------------

def summarize(
    pages: list[tuple[int, str]],
    *,
    dedup_key: Callable[[str], Iterable[str]] | None = None,
    sample_urls: list[str] | None = None,
    mechanism: str = "url",
    stopped_reason: str = "exhausted",
) -> PaginationSummary:
    """Compute a PaginationSummary from collected pages.

    If `dedup_key` is provided, it's called on each page's HTML and the union
    of items is counted (assumes callable returns an iterable of stable keys).
    """
    total = 0
    seen: set[str] = set()
    for _, body in pages:
        if dedup_key is None:
            total += 1
            continue
        try:
            keys = list(dedup_key(body))
        except Exception:
            keys = []
        for k in keys:
            if k in seen:
                continue
            seen.add(k)
            total += 1

    return PaginationSummary(
        mechanism=mechanism,
        page_count=len(pages),
        total_items=total,
        duplicate_count=max(0, sum(1 for _, b in pages if dedup_key is not None
                                    for _ in dedup_key(b)) - total),
        sample_url_per_page=sample_urls or [],
        stopped_reason=stopped_reason,
    )


# ----- module smoke ----------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    # Synthetic self-test: 2 distinct pages, with the third fetch repeated
    # (signature stop fires before a third page is appended).
    page_bodies = {
        0: "<html><ul><li>item-1</li><li>item-2</li></ul></html>",
        1: "<html><ul><li>item-3</li></ul></html>",
        2: "<html><ul><li>item-3</li></ul></html>",  # identical body -> sig stop
        3: "<html>No results found.</html>",
    }

    def fake_fetch(url: str) -> str:
        if "page=2" in url:
            return page_bodies[2]
        if "page=1" in url:
            return page_bodies[1]
        return page_bodies[0]

    pages = fetch_all_pages(fake_fetch, url="https://example.test/page",
                            dedup_key=lambda b: re.findall(r"<li>(.*?)</li>", b))
    summary = summarize(pages,
                        dedup_key=lambda b: re.findall(r"<li>(.*?)</li>", b))
    assert summary.page_count == 2, f"expected 2 pages got {summary.page_count}"
    assert summary.total_items == 3, f"expected 3 items got {summary.total_items}"
    assert summary.duplicate_count == 0, f"expected 0 duplicates got {summary.duplicate_count}"
    print(f"OK -- {summary}")
