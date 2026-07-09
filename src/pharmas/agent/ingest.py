"""Tier-routed raw ingestion: convert the chosen source(s) into an unmapped
JSON/CSV dump. No schema mapping happens here — that's map_and_validate's job.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def ingest_file(file_path: str, company_dir: Path) -> list[dict[str, Any]]:
    """Parse a downloaded file (csv/xlsx/pdf) into a list of dicts.

    PDF falls back to pdfplumber table extraction; messy PDFs may produce
    a near-empty list, in which case the user should pick the webpage.
    """
    p = Path(file_path)
    suffix = p.suffix.lower()
    if suffix in (".csv", ".tsv"):
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
        return df.to_dict(orient="records")
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(p, dtype=str).astype(str)
        return df.to_dict(orient="records")
    if suffix == ".pdf":
        import pdfplumber
        rows: list[dict[str, Any]] = []
        with pdfplumber.open(p) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    if not table or not table[0]:
                        continue
                    header = [str(h).strip() for h in table[0]]
                    for raw in table[1:]:
                        if not any(raw):
                            continue
                        row = dict(zip(header, [str(c).strip() if c else "" for c in raw]))
                        rows.append(row)
        return rows
    raise ValueError(f"unsupported file type: {suffix}")


def ingest_webpage(html_path: str, company_dir: Path,
                   source_url: str | None = None,
                   pagination: dict[str, Any] | None = None,
                   probe_results: dict[str, Any] | None = None,
                   ) -> list[dict[str, Any]]:
    """Parse a saved HTML page into a list of row dicts. Falls back to
    scrapling when the static parse yields nothing (JS-widget case).

    Auto-detects URL pagination: if the saved HTML / source_url mentions a
    `?page=` (or `?p=`, `?offset=`) shape, the relevant pages are fetched
    and parsed in a loop via `agent.pagination.fetch_all_pages`.

    When `probe_results` carries `webpage.requires_interaction=True` (SPA
    shell, data-only-after-JS, no embedded JSON), the static-parse path is
    bypassed: the agent first tries the cheap `spa_candidate_endpoints`
    URLs from the probe; on miss it writes a `raw_pipeline_meta.json` and
    returns `[]`, telling the caller to drive the widget via Playwright
    + `agent.pagination.discover_spa_endpoints_playwright`.

    For JS widgets with `Load more` / infinite scroll / filter combinations,
    auto-detection is intentionally a no-op here -- those need a real
    Playwright driver in the per-company `scrape_pipeline.py` (the helper
    `agent.pagination.loop_until_idle` / `infinite_scroll` / `exhaust_filters`
    handles them). Passing `pagination={"skip_auto_loop": True}` disables the
    URL-paginated auto-detect path entirely.
    """
    text = Path(html_path).read_text(errors="ignore")

    # ---- SPA-aware early branch ------------------------------------------
    spa_block = (probe_results or {}).get("webpage", {}) or {}
    if spa_block.get("requires_interaction"):
        rows = _try_spa_candidates(spa_block.get("spa_candidate_endpoints") or [])
        if rows:
            _write_pagination_meta(company_dir, mechanism="spa_endpoint",
                                   total_items=len(rows),
                                   sample=str(spa_block.get("spa_signature")))
            return rows
        # No candidate endpoint worked -- stop and ask for a Playwright driver.
        print(
            f"[agent.ingest_webpage] SPA detected (requires_interaction=True) "
            f"for {source_url or html_path}: no cheap JSON endpoint recovered. "
            f"Write src/pharmas/<company>/scrape_pipeline.py using "
            f"agent.pagination.discover_spa_endpoints_playwright + "
            f"loop_until_idle/exhaust_filters."
        )
        _write_spa_stop_meta(company_dir, spa_block, source_url)
        return []

    if pagination is None:
        pagination = _auto_detect_pagination(text, source_url)
    elif pagination.get("skip_auto_loop"):
        pagination = None

    # ---- URL-paginated Tier 1/2 path -------------------------------------
    if pagination and pagination.get("mechanism") == "url" and source_url:
        try:
            import requests as _requests
            from . import pagination as _pg

            urls = pagination.get("page_urls")
            if not urls:
                urls = [source_url] + [
                    _pg._set_query(source_url,
                                   **{pagination["page_param"]: i})
                    for i in range(1, pagination.get("max_pages", 50))
                ]
            rows: list[dict[str, Any]] = []
            for u in urls:
                try:
                    body = _requests.get(u, timeout=30,
                                         headers={"User-Agent": _USER_AGENT}).text
                except Exception:
                    continue
                page_rows = _parse_static_tables(body) or _flatten_json(_try_next_data(body))
                if page_rows:
                    rows.extend(page_rows)
            if rows:
                _write_pagination_meta(company_dir, mechanism="url",
                                      page_count=len(urls),
                                      total_items=len(rows))
                return rows
        except Exception:
            pass

    # ---- single-page paths (unchanged) -----------------------------------
    if "__NEXT_DATA__" in text:
        m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      text, re.DOTALL)
        if m:
            try:
                blob = json.loads(m.group(1))
                rows = _flatten_json(blob)
                if rows:
                    return rows
            except json.JSONDecodeError:
                pass

    rows = _parse_static_tables(text)
    if rows:
        return rows

    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(source_url or html_path, stealthy_headers=True)
        rows = _parse_static_tables(page.text_content or "")
        if rows:
            return rows
    except Exception:
        pass

    try:
        from scrapling.fetchers import StealthyFetcher
        page = StealthyFetcher.fetch(source_url or html_path)
        rows = _parse_static_tables(page.text_content or "")
        return rows
    except Exception:
        return []


_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _try_spa_candidates(candidate_urls: list[str]) -> list[dict[str, Any]]:
    """For each candidate URL, GET it (cheap, 5s timeout) and try to flatten
    any JSON list-of-dicts the body contains. Returns the first non-empty
    flattened result, or []."""
    if not candidate_urls:
        return []
    import requests as _requests
    for url in candidate_urls:
        try:
            r = _requests.get(url, timeout=5,
                              headers={"User-Agent": _USER_AGENT,
                                       "Accept": "application/json,text/plain,*/*"})
        except Exception:
            continue
        ctype = r.headers.get("Content-Type", "").lower()
        if "json" in ctype or r.text.lstrip().startswith(("{", "[")):
            try:
                blob = r.json()
            except Exception:
                try:
                    blob = json.loads(r.text)
                except Exception:
                    continue
            rows = _flatten_json(blob)
            if rows:
                return rows
    return []


def _write_spa_stop_meta(company_dir: Path, spa_block: dict[str, Any],
                          source_url: str | None) -> None:
    """Write the structured 'needs a Playwright driver' sidecar so finalize
    can render it and downstream users see the next-action message."""
    try:
        import json as _json
        out = company_dir / "raw_pipeline_meta.json"
        payload = {
            "mechanism": "spa",
            "requires_interaction": True,
            "source_url": source_url,
            "spa_signature": spa_block.get("spa_signature"),
            "candidate_endpoints": spa_block.get("spa_candidate_endpoints") or [],
            "next_action": (
                "Write src/pharmas/<company>/scrape_pipeline.py using "
                "agent.pagination.discover_spa_endpoints_playwright + "
                "loop_until_idle / exhaust_filters to drive the widget."
            ),
        }
        out.write_text(_json.dumps(payload, indent=2, default=str))
    except Exception:
        pass


def _auto_detect_pagination(text: str, source_url: str | None
                             ) -> dict[str, Any] | None:
    """Cheap signal sweep for URL pagination. Returns a pagination dict if
    it looks paginated and the caller has a source_url to iterate, else None.
    Load-more / infinite-scroll / filter signals are ignored here -- those
    are routed through a real scrape_pipeline.py."""
    if not source_url:
        return None
    # `?page=2` or `?p=2` link inside the HTML
    m = re.search(
        r"<a[^>]+href=[\"']([^\"']*(?:\?|&)(?:page|p|paged|offset|start)=2[^\"']*)[\"']",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    sample = m.group(1)
    # figure out which param is used
    pm = re.search(r"(?:[\?&])(page|p|paged|offset|start)=2", sample, re.IGNORECASE)
    if not pm:
        return None
    return {"mechanism": "url", "page_param": pm.group(1).lower(),
            "page_urls": None, "max_pages": 50}


def _try_next_data(text: str) -> dict[str, Any] | None:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                  text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _write_pagination_meta(company_dir: Path, **fields: Any) -> None:
    """Best-effort sidecar JSON so finalize can render a Pagination section."""
    try:
        import json as _json
        out = company_dir / "raw_pipeline_meta.json"
        out.write_text(_json.dumps(fields, indent=2, default=str))
    except Exception:
        pass


def merge_sources(*sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concatenate raw rows from multiple sources. Each row gains a `_source`
    field. Caller is responsible for de-duplication in map_and_validate."""
    merged: list[dict[str, Any]] = []
    for i, rows in enumerate(sources):
        for r in rows:
            merged.append({**r, "_source": i})
    return merged


def write_raw(rows: list[dict[str, Any]], company_dir: Path) -> dict[str, str]:
    """Dump raw rows to raw_pipeline.json + raw_pipeline.csv in company_dir."""
    company_dir.mkdir(parents=True, exist_ok=True)
    json_path = company_dir / "raw_pipeline.json"
    csv_path = company_dir / "raw_pipeline.csv"

    with open(json_path, "w") as fh:
        json.dump(rows, fh, indent=2, default=str)

    if rows:
        keys: list[str] = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in keys})

    return {"json": str(json_path), "csv": str(csv_path)}


def _parse_static_tables(html: str) -> list[dict[str, Any]]:
    """Parse server-rendered HTML tables (no JS) into row dicts."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for table in soup.find_all("table"):
        header_cells = table.find("thead")
        if header_cells is None:
            first_tr = table.find("tr")
            if first_tr is None:
                continue
            headers = [th.get_text(strip=True) for th in first_tr.find_all(["th", "td"])]
        else:
            headers = [th.get_text(strip=True) for th in header_cells.find_all(["th", "td"])]
        if not headers:
            continue
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells or len(cells) != len(headers):
                continue
            row = {h: c.get_text(" ", strip=True) for h, c in zip(headers, cells)}
            if any(v for v in row.values()):
                rows.append(row)
    return rows


def _flatten_json(blob: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Best-effort: if blob contains a list of dicts anywhere, return it."""
    if isinstance(blob, list):
        if all(isinstance(x, dict) for x in blob):
            return blob
        return [blob]
    if isinstance(blob, dict):
        for key, val in blob.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return [{**x, "_path": f"{prefix}{key}"} for x in val]
            if isinstance(val, dict):
                nested = _flatten_json(val, f"{prefix}{key}.")
                if nested:
                    return [{**x, "_path": f"{prefix}{key}{x.get('_path','')}"}
                            for x in nested]
    return []