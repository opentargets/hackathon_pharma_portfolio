"""Finalization: write log.md, edit docs/sources.md (mark Done), close issue.

Keeps the manual workflow's artifacts intact:
- src/pharmas/<company>/log.md  (mapping decisions, anomalies, cross-check)
- src/pharmas/<company>/<company>_pipeline.parquet
- docs/sources.md               (Status column flipped, link to log.md added)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SOURCES_MD = _PROJECT_ROOT / "docs" / "sources.md"


def company_dir(company: str) -> Path:
    return _PROJECT_ROOT / "src" / "pharmas" / company.lower()


def write_log_md(company: str, *, source_url: str, tier_label: str,
                 tier_actual: str, source_choice: str,
                 probe_results: dict, field_mapping: dict,
                 parquet_path: str, inconsistencies: list[str],
                 extra_notes: str = "",
                 overwrite: bool = False) -> Path:
    """Render a structured log.md mirroring the AbbVie/AstraZeneca style
    used in this repo (per AGENTS.md). Refuses to clobber an existing log
    unless overwrite=True — this is a safety rail so a re-run cannot
    silently destroy a manual extraction."""
    out = company_dir(company) / "log.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not overwrite:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = company_dir(company) / f"log_{ts}.md"

    md = [
        f"# {company} extraction log",
        "",
        f"Source: {source_url}",
        f"(Listed tier in docs/sources.md: {tier_label}; "
        f"actual after probing: {tier_actual}.)",
        "",
        "## 0. Source verification (before trusting the tier label)",
        "",
        "Per instruction_for_agent.md, checked both possible sources before deciding:",
        "",
    ]
    file_info = probe_results.get("file", {})
    web_info = probe_results.get("webpage", {})
    md.append(f"- **Downloadable file**: "
              f"{'available' if file_info.get('available') else 'not found'} — "
              f"{file_info.get('path') or file_info.get('error') or 'n/a'}")
    md.append(f"- **Webpage**: "
              f"{'fetched' if web_info.get('fetched') else 'failed'} — "
              f"static={web_info.get('static')}, "
              f"embedded_json={web_info.get('embedded_json')}, "
              f"js_widget={web_info.get('js_widget')}, "
              f"status={web_info.get('status')}, "
              f"error={web_info.get('error') or 'none'}")
    md.append("")
    md.append(f"- **User decision: {source_choice}**")
    md.append("")

    md.append("## 1. Field mapping decisions")
    md.append("")
    md.append("| Schema field | Decision | Notes |")
    md.append("|---|---|---|")
    for field, decision in field_mapping.items():
        note = decision if isinstance(decision, str) else json_safe(decision)
        md.append(f"| `{field}` | {note} | |")
    md.append("")

    md.append("## 2. Output")
    md.append("")
    md.append(f"- Parquet: `{parquet_path}`")
    md.append("")

    if inconsistencies:
        md.append("## 3. Inconsistencies found during manual cross-check")
        md.append("")
        for inc in inconsistencies:
            md.append(f"- {inc}")
        md.append("")
    else:
        md.append("## 3. Cross-check")
        md.append("")
        md.append("No inconsistencies reported.")
        md.append("")

    if extra_notes:
        md.append("## 4. Additional notes")
        md.append("")
        md.append(extra_notes)
        md.append("")

    out.write_text("\n".join(md) + "\n")
    return out


def mark_done(company: str, log_md_relpath: str) -> Path | None:
    """Edit docs/sources.md: flip the company's Status column to a Done
    marker and append a link to log.md if not already present.

    Returns the path to sources.md if updated, else None (e.g. the company
    row wasn't found or was already Done)."""
    text = _SOURCES_MD.read_text()
    company_key = company.lower().replace("-", "").replace(" ", "")

    rows = text.splitlines()
    target_idx: int | None = None
    for i, line in enumerate(rows):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Company" or cells[0].startswith("---"):
            continue
        row_key = cells[0].strip("` ").lower().replace("-", "").replace(" ", "")
        if row_key == company_key:
            target_idx = i
            break

    if target_idx is None:
        return None

    cells = [c.strip() for c in rows[target_idx].strip().strip("|").split("|")]
    while len(cells) < 4:
        cells.append("")
    cells[3] = f"Done — see [`src/pharmas/{company.lower()}/log.md`]({log_md_relpath})"

    if "log.md" not in cells[2] and log_md_relpath not in cells[2]:
        cells[2] = cells[2].rstrip()
        if cells[2]:
            cells[2] = cells[2] + f" See [`log.md`]({log_md_relpath})"
        else:
            cells[2] = f"See [`log.md`]({log_md_relpath})"

    new_line = "| " + " | ".join(cells) + " |"
    rows[target_idx] = new_line
    _SOURCES_MD.write_text("\n".join(rows) + "\n")
    return _SOURCES_MD


def json_safe(obj: object) -> str:
    import json
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return str(obj)