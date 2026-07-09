"""Probe a company's pipeline source: locate a downloadable file AND/OR fetch
the live webpage (cheap curl first). Used by the load_sources_md → classify_tier
edge of the graph to decide what to feed into ingest_raw.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_EMBEDDED_JSON_HINTS = (
    "__NEXT_DATA__",
    'type="application/ld+json"',
    'type="application/json"',
    "window.__INITIAL_STATE__",
    "pipelineData",
)


def _safe_filename(url: str, suffix: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "pipeline_page"
    if not name.endswith(suffix):
        name = f"{name}{suffix}"
    return name


def probe_file(source_url: str, notes: str, company_dir: Path) -> dict[str, Any]:
    """Locate a downloadable file (PDF/CSV/xlsx). Looks at:
    - source_url itself, if it ends with a known extension
    - notes for explicit file links
    - common sibling paths (/pipeline.pdf, /pipeline.csv, etc.)

    Returns {"available": bool, "path": str | None, "url": str | None,
             "kind": "pdf"|"csv"|"xlsx"|None, "error": str | None}.
    """
    candidates: list[str] = []
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path_dir = source_url.rsplit("/", 1)[0] + "/"

    if re.search(r"\.(pdf|csv|xlsx?)$", source_url, re.IGNORECASE):
        candidates.append(source_url)

    for ext in ("pdf", "csv", "xlsx"):
        for slug in ("pipeline", "Pipeline", "development-pipeline"):
            candidates.append(urljoin(path_dir, f"{slug}.{ext}"))

    file_match = re.search(r"`(https?://[^`]*\.(?:pdf|csv|xlsx?))`", notes)
    if file_match:
        candidates.insert(0, file_match.group(1))

    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = requests.head(url, allow_redirects=True, timeout=15,
                              headers={"User-Agent": _USER_AGENT})
            if r.status_code >= 400:
                continue
            ctype = r.headers.get("Content-Type", "").lower()
            if not any(t in ctype for t in ("pdf", "csv", "excel", "spreadsheet",
                                              "octet-stream", "text/plain")):
                continue
            kind = _kind_from_url(url, ctype)
            fname = _safe_filename(url, f".{kind}" if kind else "")
            dest = company_dir / fname
            with requests.get(url, stream=True, timeout=60,
                              headers={"User-Agent": _USER_AGENT}) as gr:
                gr.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in gr.iter_content(chunk_size=1 << 14):
                        fh.write(chunk)
            return {"available": True, "path": str(dest), "url": url,
                    "kind": kind, "error": None}
        except requests.RequestException as exc:
            continue

    return {"available": False, "path": None, "url": None,
            "kind": None, "error": "no downloadable file matched"}


def probe_webpage(source_url: str, company_dir: Path) -> dict[str, Any]:
    """Cheap curl of the live pipeline page. Saves HTML and checks for
    embedded JSON blobs (Next.js data, ld+json, etc.) and JS-widget signals.
    Also runs a cheap pagination probe -- tries `?page=2`, `?p=2`, `?offset=`
    and a "Load more" regex sweep; and an SPA-shape detector for shells where
    data only mounts after JS (no embedded JSON).

    Returns {"fetched": bool, "path": str | None, "static": bool,
             "embedded_json": bool, "js_widget": bool, "status": int,
             "content_type": str, "error": str | None,
             "has_pagination": bool, "pagination_mechanism": str | None,
             "detected_total_pages": int | None,
             "first_page_url": str | None,
             "load_more_selector_hint": str | None,
             "next_page_selector_hint": str | None,
             "spa_signature": dict | None,
             "spa_candidate_endpoints": list[str],
             "requires_interaction": bool}.
    """
    try:
        r = requests.get(source_url, timeout=30,
                         headers={"User-Agent": _USER_AGENT,
                                  "Accept": "text/html,application/json,*/*"})
    except requests.RequestException as exc:
        return {"fetched": False, "path": None, "static": False,
                "embedded_json": False, "js_widget": False,
                "status": 0, "content_type": "", "error": str(exc),
                "has_pagination": False, "pagination_mechanism": None,
                "detected_total_pages": None, "first_page_url": None,
                "load_more_selector_hint": None,
                "next_page_selector_hint": None,
                "spa_signature": None,
                "spa_candidate_endpoints": [],
                "requires_interaction": False}

    ctype = r.headers.get("Content-Type", "").lower()
    looks_like_html = "text/html" in ctype or "application/xhtml" in ctype

    body = r.text if looks_like_html else ""
    embedded = any(h in body for h in _EMBEDDED_JSON_HINTS)
    js_widget_signals = (
        "rendered dynamically" in body.lower()
        or "this app requires javascript" in body.lower()
        or re.search(r'<script[^>]+src="[^"]*\.(?:js|ts)[^"]*"', body) is not None
        and not embedded
    )

    dest: Path | None = None
    if body and r.status_code == 200:
        dest = company_dir / "pipeline_page.html"
        if dest.exists():
            import datetime as _dt
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = company_dir / f"pipeline_page_{stamp}.html"
        dest.write_text(body)

    pagination_hints = _detect_pagination_hints(source_url, body)

    # Compute SPA signature and candidate endpoints AFTER pagination hints so
    # an existing "load_more" match still wins over the SPA-detector's defaults
    spa_block = _detect_spa_signature(body, source_url)
    spa_candidates = [e.url for e in
                      _safe_call_spa_html(body, source_url)]

    static_rows = _safe_static_table_count(body)
    data_total = (spa_block or {}).get("data_results_count")
    incomplete_vs_published = (
        data_total is not None and static_rows < data_total // 2
    )
    requires_interaction = (
        bool(spa_block)
        and not embedded
        and (incomplete_vs_published or static_rows <= 1)
    )

    static = (
        r.status_code == 200
        and looks_like_html
        and bool(body)
        and not js_widget_signals
        and not requires_interaction
    )

    return {"fetched": r.status_code == 200, "path": str(dest) if dest else None,
            "static": static, "embedded_json": embedded,
            "js_widget": js_widget_signals and not embedded or requires_interaction,
            "status": r.status_code, "content_type": ctype,
            "error": None if r.status_code == 200 else f"HTTP {r.status_code}",
            **pagination_hints,
            "spa_signature": spa_block,
            "spa_candidate_endpoints": spa_candidates,
            "requires_interaction": requires_interaction}


def _detect_pagination_hints(source_url: str, body: str) -> dict[str, Any]:
    """Lightweight pagination probe: cheap regex sweep on the initial HTML,
    then up to 2 extra requests to confirm URL pagination.

    Capped so `probe_file + probe_webpage` stays fast. Heavy lifting
    (cartesian filter enumeration, full drain) belongs to the per-company
    scrape_pipeline.py, not to probe.
    """
    hints: dict[str, Any] = {
        "has_pagination": False,
        "pagination_mechanism": None,
        "detected_total_pages": None,
        "first_page_url": None,
        "load_more_selector_hint": None,
        "next_page_selector_hint": None,
    }
    if not body:
        return hints

    lowered = body.lower()

    load_more_re = re.search(
        r"<(\w+)[^>]*\b(?:class|id|aria-label|text)=[\"'][^\"']*"
        r"(?:load\s*more|show\s*more|see\s*more|next\s*page|more\s*results|"
        r"load-more|load-more-btn|show-more-results)"
        r"[^\"']*[\"'][^>]*>",
        lowered,
    )
    if load_more_re:
        hints["has_pagination"] = True
        hints["pagination_mechanism"] = "load_more"
        hints["load_more_selector_hint"] = load_more_re.group(0)[:160]
        # Best-effort: a tight "button.load-more" or "a.load-more" hint.
        # Require the class to be a load-more-ish word, not just contain "more".
        tight = re.search(
            r"<(\w+)[^>]*class=[\"'][^\"']*"
            r"(?:load-?more|show-?more|more-?(?:results|pages|items|programs|assets))"
            r"[^\"']*[\"']",
            lowered,
        )
        if tight:
            cls = re.search(r"class=[\"']([^\"']+)[\"']", tight.group(0))
            if cls:
                hints["load_more_selector_hint"] = (
                    f"{tight.group(1)}.{cls.group(1).split()[0]}"
                )

    next_re = re.search(
        r"<a[^>]+href=[\"']([^\"']*(?:\?|&)(?:page|p|paged|offset|start)=2[^\"']*)[\"']",
        body,
        re.IGNORECASE,
    )
    if next_re:
        hints["has_pagination"] = True
        if not hints["pagination_mechanism"]:
            hints["pagination_mechanism"] = "url"
            hints["first_page_url"] = source_url
            hints["next_page_selector_hint"] = next_re.group(1)
            # sanity check: is `?page=2` actually different from page 1?
            try:
                from . import pagination as _pg
                probe = _pg.detect_url_pagination(
                    lambda u: requests.get(u, timeout=15,
                                           headers={"User-Agent": _USER_AGENT}).text,
                    url=source_url, max_probes=5,
                )
                if probe["has_pagination"]:
                    hints["detected_total_pages"] = probe["detected_total_pages"]
                    hints["first_page_url"] = probe["page_urls"][0]
                    hints["next_page_selector_hint"] = probe["page_urls"][1]
            except Exception:
                pass

    return hints


def _kind_from_url(url: str, ctype: str) -> str | None:
    u = url.lower()
    if u.endswith(".pdf") or "pdf" in ctype:
        return "pdf"
    if u.endswith(".csv") or "csv" in ctype or "text/plain" in ctype:
        return "csv"
    if u.endswith(".xlsx") or u.endswith(".xls") or "spreadsheet" in ctype or "excel" in ctype:
        return "xlsx"
    return None


_PAGE_SIZE_TRIPLETS = (
    ("10", "20", "40"),
    ("25", "50", "100"),
    ("12", "24", "36"),
    ("10", "25", "50"),
    ("15", "30", "60"),
)


def _detect_spa_signature(body: str, source_url: str) -> dict[str, Any] | None:
    """Return a small SPA-signature dict when the static HTML looks like a
    JavaScript-only widget (no embedded data, server-rendered filters only).

    Returns None when none of the heuristics trip. The signature is the basis
    for `requires_interaction` downstream; never load-bearing on its own.
    """
    if not body:
        return None

    # 1) page-size <select> detection: scan each <select> for option values
    # matching a known page-size triplet.
    page_size_selects: list[str] = []
    for sel_match in re.finditer(
        r"<select\b[^>]*>(.*?)</select>", body, re.IGNORECASE | re.DOTALL,
    ):
        inner = sel_match.group(1)
        opts = re.findall(r"<option\b[^>]*value=[\"']([^\"']+)[\"']", inner)
        for triple in _PAGE_SIZE_TRIPLETS:
            if all(t in opts for t in triple):
                page_size_selects.append(sel_match.group(0)[:80])
                break

    # 2) canvas-heavy: counted canvas tags (immersive SPA hint)
    canvas_count = len(re.findall(r"<canvas\b", body, re.IGNORECASE))

    # 3) filter markers: data-attr-filter= or data-attr-id= (Drupal-style)
    filter_marker_count = len(re.findall(r"data-attr-filter=", body))

    # 4) explicit results counter
    counter_m = re.search(
        r"data-(?:product|results|total)-count=[\"'](\d+)[\"']", body
    )
    data_results_count = int(counter_m.group(1)) if counter_m else None

    # 5) Drupal generator without an obvious JSON:API endpoint script
    drupal_generator = bool(re.search(
        r'<meta\s+name=["\']Generator["\']\s+content=["\']Drupal\s+\d+',
        body, re.IGNORECASE,
    ))
    jsonapi_script = bool(re.search(r"/jsonapi|/views/api", body))

    sig = {
        "page_size_selects": page_size_selects,
        "canvas_count": canvas_count,
        "filter_marker_count": filter_marker_count,
        "data_results_count": data_results_count,
        "drupal_generator": drupal_generator,
        "jsonapi_script": jsonapi_script,
    }

    # Threshold: at least two independent signals, or canvas-heavy + filters,
    # or drupal-without-jsonapi plus filters. Single weak signals don't trip.
    strong = (
        sig["drupal_generator"] and not sig["jsonapi_script"]
        and sig["filter_marker_count"] >= 4
    )
    multi = (
        sig["canvas_count"] >= 1
        and sig["filter_marker_count"] >= 4
    )
    snapshot_select = (
        len(sig["page_size_selects"]) >= 1
        and sig["filter_marker_count"] >= 3
    )
    if strong or multi or snapshot_select:
        return sig
    return None


def _safe_call_spa_html(body: str, source_url: str) -> list:
    """Wrap `pagination.discover_spa_endpoints_html` so a buggy regex won't
    crash probe. Returns [] on exception."""
    if not body:
        return []
    try:
        from .pagination import discover_spa_endpoints_html
        return discover_spa_endpoints_html(body, source_url)
    except Exception:
        return []


def _safe_static_table_count(body: str) -> int:
    """Return the count of "data-looking" rows in the static HTML -- rows in
    tables whose headers mention pipeline-relevant columns (compound,
    indication, phase, molecule, therapeutic area, etc.). Glossary or nav
    tables don't count, which is critical for SPAs whose only static <table>
    is a footer glossary."""
    if not body:
        return 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, "html.parser")
        keep = ("compound", "indication", "phase", "molecule", "therapeutic",
                "mechanism", "program", "asset", "product", "drug",
                "modality", "area of focus", "submission")
        n = 0
        for table in soup.find_all("table"):
            first_tr = table.find("tr")
            if first_tr is None:
                continue
            headers = [th.get_text(strip=True).lower()
                       for th in first_tr.find_all(["th", "td"])]
            if not any(any(k in h for k in keep) for h in headers):
                continue
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all(["td", "th"])
                if cells and len(cells) == len(headers):
                    n += 1
        return n
    except Exception:
        return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: python -m pharmas.agent.probe <company> <source_url>")
        sys.exit(2)
    company, url = sys.argv[1], sys.argv[2]
    company_dir = Path(__file__).resolve().parents[1] / company.lower()
    company_dir.mkdir(exist_ok=True)
    print(json.dumps({"file": probe_file(url, "", company_dir),
                      "webpage": probe_webpage(url, company_dir)}, indent=2))