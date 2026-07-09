"""SPA probe demo.

Reads a saved pipeline_page.html (no network), feeds it through the agent's
SPA-detection heuristics and the static endpoint-discovery helper, and prints
a verdict: would `agent.ingest_webpage` know to ask for a Playwright driver,
or would it just write the rows it found into raw_pipeline.json?

This is the working reference for what `probe_webpage -> ingest_webpage`
should look like when the source is a JavaScript-only widget (data mounts
*after* JS, no embedded JSON blob). The Pfizer immersive widget is the
textbook example -- see src/pharmas/pfizer/pipeline_page.html, the saved
shell that returned only 10 of 96 pipeline rows from a static parse.

Usage:
    uv run python -m pharmas.agent.examples.spa_probe_demo [path/to/pipeline_page.html]

Default path is src/pharmas/pfizer/pipeline_page.html so that running the demo
without arguments demonstrates the SPA-detection verdict against a real saved
page. No Playwright is invoked; the demo is fully offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _resolve_target() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    # spa_probe_demo.py  -> examples  -> agent  -> pharmas  -> src  -> repo
    repo = Path(__file__).resolve().parents[4]
    default = repo / "src" / "pharmas" / "pfizer" / "pipeline_page.html"
    if not default.exists():
        sys.stderr.write(
            f"[spa_probe_demo] default {default} not found; pass an HTML path.\n"
        )
        sys.exit(2)
    return default


def main() -> None:
    html_path = _resolve_target()
    if not html_path.exists():
        sys.stderr.write(f"[spa_probe_demo] missing {html_path}\n")
        sys.exit(2)

    html = html_path.read_text(errors="ignore")
    # When called without arguments against the saved Pfizer HTML, point the
    # discovery helpers at the real Pfizer URL so candidates resolve to real
    # rather than file:// URLs in the demo's output. When the user passes an
    # arbitrary path, fall back to file:// for the demo's bookkeeping.
    default_repo = Path(__file__).resolve().parents[4]
    is_pfizer_default = (
        len(sys.argv) == 1
        and html_path == default_repo / "src" / "pharmas" / "pfizer" / "pipeline_page.html"
    )
    source_url = (
        "https://www.pfizer.com/science/drug-product-pipeline"
        if is_pfizer_default else html_path.resolve().as_uri()
    )

    from pharmas.agent.probe import (
        _detect_spa_signature,
        _safe_call_spa_html,
        _safe_static_table_count,
    )
    from pharmas.agent.pagination import discover_spa_endpoints_html

    sig = _detect_spa_signature(html, source_url)
    candidates = discover_spa_endpoints_html(html, source_url)
    static_rows = _safe_static_table_count(html)

    print(f"# SPA probe demo")
    print(f"file:           {html_path}")
    print(f"size_bytes:     {len(html)}")
    print(f"static_rows:    {static_rows}")
    print()

    if sig is None:
        print("verdict:        not an SPA shell")
        print("                (no canvas + filters + page-size select + Drupal")
        print("                 combination trip the multi-signal detector).")
        print("                ingest_webpage would fall through to the static")
        print("                table / Next.js / scrapling path as before.")
        return

    data_total = sig.get("data_results_count")
    incomplete = (
        data_total is not None and static_rows < data_total // 2
    )
    requires_interaction = bool(sig) and (incomplete or static_rows <= 1)

    print("verdict:        SPA shell detected")
    print(f"signature:      {json.dumps(sig, indent=14)[:600]}")
    print()
    print(f"requires_interaction: {requires_interaction}")
    print(f"  (data_results_count={data_total}, static_rows={static_rows},"
          f" data_total // 2 = {data_total // 2 if data_total else 'n/a'})")
    print()

    if not requires_interaction:
        print("ingest_webpage: would parse the static table and emit those rows")
        print("                (likely an incomplete sample -- re-check the")
        print("                comparison against the page's published total).")
        return

    print("ingest_webpage: writes raw_pipeline_meta.json with")
    print("                mechanism='spa', requires_interaction=True, and a")
    print("                'next_action' message naming the helpers to use.")
    print("                returns [] -- the per-pharma driver lives in")
    print("                src/pharmas/<company>/scrape_pipeline.py")
    print()

    print(f"static-scan candidate endpoints ({len(candidates)}):")
    for ep in candidates[:8]:
        print(f"  - {ep.url}")
    if not candidates:
        print("  (none -- the XHR lives inside a JS bundle that probe.py cannot")
        print("   inspect without running Playwright. Discover_spa_endpoints_playwright")
        print("   inside scrape_pipeline.py will catch it.)")


if __name__ == "__main__":
    main()
