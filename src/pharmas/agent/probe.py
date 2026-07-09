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

    Returns {"fetched": bool, "path": str | None, "static": bool,
             "embedded_json": bool, "js_widget": bool, "status": int,
             "content_type": str, "error": str | None}.
    """
    try:
        r = requests.get(source_url, timeout=30,
                         headers={"User-Agent": _USER_AGENT,
                                  "Accept": "text/html,application/json,*/*"})
    except requests.RequestException as exc:
        return {"fetched": False, "path": None, "static": False,
                "embedded_json": False, "js_widget": False,
                "status": 0, "content_type": "", "error": str(exc)}

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

    static = (
        r.status_code == 200
        and looks_like_html
        and bool(body)
        and not js_widget_signals
    )

    return {"fetched": r.status_code == 200, "path": str(dest) if dest else None,
            "static": static, "embedded_json": embedded,
            "js_widget": js_widget_signals and not embedded,
            "status": r.status_code, "content_type": ctype,
            "error": None if r.status_code == 200 else f"HTTP {r.status_code}"}


def _kind_from_url(url: str, ctype: str) -> str | None:
    u = url.lower()
    if u.endswith(".pdf") or "pdf" in ctype:
        return "pdf"
    if u.endswith(".csv") or "csv" in ctype or "text/plain" in ctype:
        return "csv"
    if u.endswith(".xlsx") or u.endswith(".xls") or "spreadsheet" in ctype or "excel" in ctype:
        return "xlsx"
    return None


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