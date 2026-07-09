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
                   source_url: str | None = None) -> list[dict[str, Any]]:
    """Parse a saved HTML page into a list of row dicts. Falls back to
    scrapling when the static parse yields nothing (JS-widget case)."""
    text = Path(html_path).read_text(errors="ignore")

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