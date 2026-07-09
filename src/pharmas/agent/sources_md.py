"""Parse docs/sources.md to look up a company's tier and source URL."""

from __future__ import annotations

import re
from pathlib import Path


_SOURCES_MD = Path(__file__).resolve().parents[3] / "docs" / "sources.md"

_TIER_HEADING = re.compile(r"^###\s+Tier\s+(\d+)\s*[—–-]\s*(.+?)\s*$", re.MULTILINE)


def _split_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def find_company(company: str, path: Path = _SOURCES_MD) -> dict | None:
    """Find the company row in docs/sources.md. Returns dict with
    {company, source_url, notes, status, tier, tier_label} or None."""
    text = path.read_text()
    tier_for_section: list[tuple[int, int]] = []
    for m in _TIER_HEADING.finditer(text):
        tier_for_section.append((m.start(), int(m.group(1))))

    rows: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) < 4 or cells[0] == "---":
            continue
        if cells[0] == "Company":
            continue
        company_cell = cells[0].strip("` ")
        url_match = re.search(r"`([^`]+)`", cells[1])
        source_url = url_match.group(1) if url_match else cells[1]
        rows.append({
            "company": company_cell,
            "source_url": source_url,
            "notes": cells[2],
            "status": cells[3],
            "line_offset": sum(len(l) + 1 for l in text.splitlines()[:text.splitlines().index(line)]) if line in text.splitlines() else 0,
        })

    company_key = company.lower().replace("-", "").replace(" ", "")
    for row in rows:
        if row["company"].lower().replace("-", "").replace(" ", "") == company_key:
            offset = row.pop("line_offset")
            for i, (start, tier) in enumerate(tier_for_section):
                next_start = tier_for_section[i + 1][0] if i + 1 < len(tier_for_section) else len(text)
                if start <= offset < next_start:
                    row["tier"] = tier
                    break
            else:
                row["tier"] = None
            row["tier_label"] = f"Tier {row['tier']}" if row["tier"] else "Unknown"
            return row
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: python -m pharmas.agent.sources_md <company>")
        sys.exit(2)
    result = find_company(sys.argv[1])
    if result is None:
        print(f"company '{sys.argv[1]}' not found in docs/sources.md")
        sys.exit(1)
    print(result)