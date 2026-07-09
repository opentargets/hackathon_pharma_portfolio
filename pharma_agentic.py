"""Pharma extraction LangGraph flow.

Replaces the long-running manual prompt for "<Company> next: open a GitHub
issue, probe file + webpage, ask me which to use, ask me about field mapping,
write log.md + parquet, mark Done in docs/sources.md, close the issue."

Usage:
    uv run python pharma_agentic.py --company abbvie --model anthropic/claude-sonnet-4-5
    uv run python pharma_agentic.py --company gsk --model <id> --no-issue

The graph wraps the original extract → normalize → validate → retry subgraph
(from a prior version of this file) inside `map_and_validate`, surrounded by
five new gates:
    load_sources_md → create_github_issue → probe_sources → classify_tier
    → ⏸ present_sources_and_confirm → ingest_raw
    → ⏸ confirm_field_mapping → map_and_validate
    → ⏸ manual_cross_check → finalize

Each ⏸ gate reads stdin synchronously — the simplest possible interrupt
that works identically from a shell, a notebook, or another orchestrator.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, ValidationError

# Project-local imports. `schema` resolves via the src-layout editable install
# configured by pyproject.toml (see AGENTS.md / instruction_for_agent.md).
from schema import Phase, PipelineRecord

# New agent helpers (kept out of src/pharmas/<company>/ per AGENTS.md).
from pharmas.agent import finalize as finalize_mod
from pharmas.agent import gates, github, ingest, probe, sources_md


# --- State ----------------------------------------------------------------
class State(TypedDict, total=False):
    company: str
    source: str
    model: str
    out_path: str
    parquet_path: str
    log_md_path: str

    sources_md_row: dict
    tier_label: str
    tier_actual: str

    issue_url: str | None
    issue_number: str | None

    probe_results: dict
    source_choice: Literal["file", "webpage", "merged"] | None

    raw_rows: list[dict]
    raw_path: str | None
    raw_paths: dict

    field_mapping: dict

    normalized: list[dict]
    valid: list[dict]
    invalid: list[tuple]
    retry_count: int
    max_retries: int

    cross_check_paste: str | None
    cross_check_diff: dict
    inconsistencies: list[str]

    errors: list[str]


# --- Constants from the previous implementation (kept for the inner
# subgraph that does extract → normalize → validate → write). ----------------
_PHASE = {
    "preclinical": Phase.PRECLINICAL, "discovery": Phase.PRECLINICAL, "pre-ind": Phase.PRECLINICAL,
    "ind": Phase.PRECLINICAL, "early phase 1": Phase.PHASE_1,
    "phase 1": Phase.PHASE_1, "phase i": Phase.PHASE_1, "first-in-human": Phase.PHASE_1, "poc": Phase.PHASE_1,
    "phase 1/2": Phase.PHASE_1_2, "phase i/ii": Phase.PHASE_1_2, "phase 1b/2": Phase.PHASE_1_2,
    "phase 2": Phase.PHASE_2, "phase ii": Phase.PHASE_2, "proof of concept": Phase.PHASE_2,
    "phase 2/3": Phase.PHASE_2_3, "phase ii/iii": Phase.PHASE_2_3,
    "phase 3": Phase.PHASE_3, "phase iii": Phase.PHASE_3, "pivotal": Phase.PHASE_3,
    "phase 4": Phase.REGISTERED,
    "preregistration": Phase.PREREGISTRATION, "nda filed": Phase.PREREGISTRATION,
    "bla filed": Phase.PREREGISTRATION, "submitted": Phase.PREREGISTRATION, "under review": Phase.PREREGISTRATION,
    "registered": Phase.REGISTERED, "approved": Phase.REGISTERED, "marketed": Phase.REGISTERED,
    "discontinued": Phase.DISCONTINUED, "terminated": Phase.DISCONTINUED, "suspended": Phase.DISCONTINUED,
}
_TA = {
    "oncology": "Oncology", "cancer": "Oncology", "immunology": "Immunology",
    "cardiovascular": "Cardiovascular", "neuroscience": "Neuroscience",
}


# --- New graph nodes ------------------------------------------------------
def load_sources_md(state: State) -> State:
    company = state["company"]
    row = sources_md.find_company(company)
    if row is None:
        return {"errors": [f"company '{company}' not found in docs/sources.md"]}
    return {
        "sources_md_row": row,
        "source": row.get("source_url"),
        "tier_label": row.get("tier_label", "Unknown"),
    }


def create_github_issue(state: State) -> State:
    if not github.gh_available():
        return {"issue_url": None, "issue_number": None,
                "errors": state.get("errors", []) + ["gh not available; skipping issue"]}
    body = (
        f"# {state['company']} pipeline extraction\n\n"
        f"- Tier (docs/sources.md): {state.get('tier_label', 'Unknown')}\n"
        f"- Source: {state.get('source', 'n/a')}\n\n"
        "This issue will be updated when the extraction is complete "
        "(mapping decisions, parquet path, cross-check results)."
    )
    result = github.create_issue(state["company"], body)
    if result.get("error"):
        return {"errors": state.get("errors", []) + [result["error"]]}
    return {"issue_url": result.get("url"), "issue_number": result.get("number")}


def probe_sources(state: State) -> State:
    company_dir = finalize_mod.company_dir(state["company"])
    company_dir.mkdir(parents=True, exist_ok=True)

    source_url = state.get("source") or state.get("sources_md_row", {}).get("source_url")
    if not source_url:
        empty = {"available": False, "path": None, "url": None, "kind": None,
                 "error": "no source URL resolved"}
        return {"probe_results": {"file": empty, "webpage": empty}}

    file_info = probe.probe_file(
        source_url, state.get("sources_md_row", {}).get("notes", ""), company_dir
    )
    web_info = probe.probe_webpage(source_url, company_dir)

    return {"probe_results": {"file": file_info, "webpage": web_info}}


def classify_tier(state: State) -> State:
    file_info = state.get("probe_results", {}).get("file", {})
    web_info = state.get("probe_results", {}).get("webpage", {})

    if web_info.get("static") or web_info.get("embedded_json"):
        tier = 1
    elif file_info.get("available") and file_info.get("kind") in ("csv", "xlsx"):
        tier = 1
    elif file_info.get("available") and file_info.get("kind") == "pdf":
        tier = 2
    elif web_info.get("js_widget"):
        tier = 3
    else:
        tier = state.get("sources_md_row", {}).get("tier") or 3

    return {"tier_actual": f"Tier {tier}"}


def present_sources_and_confirm(state: State) -> State:
    """Gate #1: ask the user which source to use (file / webpage / merged)."""
    probes = state.get("probe_results", {})
    file_info = probes.get("file", {})
    web_info = probes.get("webpage", {})

    sys.stdout.write("\n=== SOURCE PROBE RESULTS ===\n")
    sys.stdout.write(f"  file     : "
                     f"{'available' if file_info.get('available') else 'missing'}"
                     f" ({file_info.get('kind') or 'n/a'})\n")
    sys.stdout.write(f"  webpage  : fetched={web_info.get('fetched')} "
                     f"static={web_info.get('static')} "
                     f"embedded_json={web_info.get('embedded_json')} "
                     f"js_widget={web_info.get('js_widget')}\n")
    sys.stdout.write(f"  tier (sources.md): {state.get('tier_label')} | "
                     f"tier (after probes): {state.get('tier_actual')}\n")
    sys.stdout.write("===========================\n")

    options = ["webpage", "file", "merged"]
    default_idx = 0 if web_info.get("fetched") else 1
    choice = gates.ask_choice(
        "Which source(s) should we use for ingestion?",
        options, default_index=default_idx,
    )
    return {"source_choice": choice}  # type: ignore[return-value]


def ingest_raw(state: State) -> State:
    company_dir = finalize_mod.company_dir(state["company"])
    company_dir.mkdir(parents=True, exist_ok=True)
    choice = state.get("source_choice")
    probes = state.get("probe_results", {})

    rows: list[dict] = []
    paths: dict = {}

    if choice in ("file", "merged") and probes.get("file", {}).get("available"):
        file_rows = ingest.ingest_file(probes["file"]["path"], company_dir)
        paths["file"] = probes["file"]["path"]
        rows.extend(file_rows)

    if choice in ("webpage", "merged"):
        web_info = probes.get("webpage", {})
        if web_info.get("path"):
            web_rows = ingest.ingest_webpage(
                web_info["path"], company_dir, state.get("source"),
            )
            paths["webpage"] = web_info["path"]
            rows.extend(web_rows)

    if choice == "merged":
        sources = []
        if probes.get("file", {}).get("available"):
            sources.append(ingest.ingest_file(probes["file"]["path"], company_dir))
        if probes.get("webpage", {}).get("path"):
            sources.append(ingest.ingest_webpage(probes["webpage"]["path"], company_dir, state.get("source")))
        rows = ingest.merge_sources(*sources) if sources else []

    raw_paths = ingest.write_raw(rows, company_dir)
    return {"raw_rows": rows, "raw_path": raw_paths["json"], "raw_paths": raw_paths}


def _build_mapping_questions(raw_rows: list[dict], field_mapping: dict) -> list[dict]:
    """Derive up to 4 mapping questions from the raw data shape."""
    keys = set()
    for r in raw_rows[:50]:
        keys.update(r.keys())

    qs: list[dict] = []

    if any(k for k in keys if k and ("name" in k.lower() or "compound" in k.lower() or "asset" in k.lower())):
        qs.append({
            "key": "asset_name_column",
            "prompt": "Which column holds the canonical asset name? "
                      "(compound code preferred over trade/brand per AGENTS.md preference.)",
            "choices": sorted([k for k in keys if k and ("name" in k.lower() or "compound" in k.lower())]),
            "default_index": 0,
        })

    if any(k for k in keys if k and ("mechanism" in k.lower() or "moa" in k.lower() or "target" in k.lower())):
        qs.append({
            "key": "moa_column",
            "prompt": "Which column holds the mechanism of action? (None if not present.)",
            "choices": ["(none — leave MoA blank)"] + sorted([k for k in keys if k and ("mechanism" in k.lower() or "moa" in k.lower() or "target" in k.lower())]),
            "default_index": 0,
        })

    if any(k for k in keys if k and ("area" in k.lower() or "therapeutic" in k.lower())):
        qs.append({
            "key": "ta_column",
            "prompt": "Which column holds the therapeutic area?",
            "choices": sorted([k for k in keys if k and ("area" in k.lower() or "therapeutic" in k.lower())]),
            "default_index": 0,
        })

    if any(k for k in keys if k and "phase" in k.lower()):
        qs.append({
            "key": "phase_column",
            "prompt": "Which column holds the development phase?",
            "choices": sorted([k for k in keys if k and "phase" in k.lower()]),
            "default_index": 0,
        })

    return qs[:4]


def confirm_field_mapping(state: State) -> State:
    """Gate #2: ask up to 4 batched mapping questions."""
    raw_rows = state.get("raw_rows", [])
    questions = _build_mapping_questions(raw_rows, state.get("field_mapping", {}))
    if not questions:
        return {"field_mapping": state.get("field_mapping", {})}

    sys.stdout.write(f"\n=== FIELD MAPPING ({len(raw_rows)} raw rows) ===\n")
    answers = gates.ask_batched(questions)
    merged = {**state.get("field_mapping", {}), **answers}
    return {"field_mapping": merged}


def map_and_validate(state: State) -> State:
    """Wrap the inner extract → normalize → validate → write subgraph on
    state.raw_rows, applying state.field_mapping."""
    raw_rows = state.get("raw_rows", [])
    mapping = state.get("field_mapping", {})

    asset_col = mapping.get("asset_name_column") or "asset_name"
    moa_col = mapping.get("moa_column")
    ta_col = mapping.get("ta_column")
    phase_col = mapping.get("phase_column")

    if moa_col == "(none — leave MoA blank)":
        moa_col = None
    if ta_col == "(none — leave MoA blank)":
        ta_col = None

    normalized: list[dict] = []
    for row in raw_rows:
        inds = row.get("indication") or row.get("indications") or row.get("Area under investigation")
        if isinstance(inds, list):
            ind_list = [str(x) for x in inds if x]
        elif inds:
            ind_list = [str(inds)]
        else:
            ind_list = ["(unspecified)"]
        for ind in ind_list:
            raw_phase = str(row.get(phase_col, "")).strip() if phase_col else ""
            ta_raw = str(row.get(ta_col, "")).strip() if ta_col else ""
            phase_enum = _PHASE.get(raw_phase.lower()) if raw_phase else None
            normalized.append({
                "company": state["company"],
                "asset_name": str(row.get(asset_col, "")).strip() or "(unknown)",
                "mechanism_of_action": (str(row.get(moa_col)).strip() or None) if moa_col else None,
                "therapeutic_area": _TA.get(ta_raw.lower(), ta_raw.title() if ta_raw else None),
                "indication": ind,
                "phase": phase_enum.value if phase_enum else Phase.PRECLINICAL.value,
                "phase_from_source": raw_phase or None,
                "source_url": state.get("source"),
                "extraction_date": date.today().isoformat(),
                "notes": row.get("_path"),
            })

    valid, invalid = [], []
    for row in normalized:
        try:
            valid.append(PipelineRecord.model_validate(row).model_dump(mode="json"))
        except ValidationError as e:
            invalid.append((row.get("asset_name", "?"), e.errors()))

    return {"normalized": normalized, "valid": valid, "invalid": invalid}


def manual_cross_check(state: State) -> State:
    """Gate #3: ask the user to paste a sample from the live source, then
    report inconsistencies against the mapped output."""
    valid = state.get("valid", [])
    sys.stdout.write("\n=== MANUAL CROSS-CHECK ===\n")
    sys.stdout.write(f"Mapped {len(valid)} records. To catch selector bugs "
                     f"that re-reading the same raw HTML won't surface, please "
                     f"paste a manual copy/paste of the source below.\n")
    paste = gates.ask_free_text("(paste source rows; finish with ---)")

    inconsistencies: list[str] = []
    if paste.strip():
        pasted_lines = [ln.strip() for ln in paste.splitlines() if ln.strip()]
        valid_names = {str(r.get("asset_name", "")).strip().lower() for r in valid}
        pasted_assets: set[str] = set()
        for ln in pasted_lines:
            for token in ln.split("\t"):
                if len(token) > 3 and not token.isdigit():
                    pasted_assets.add(token.lower())
        missing = pasted_assets - valid_names
        if missing:
            inconsistencies.append(
                f"Names in paste but not in output: {sorted(missing)[:10]}"
                + (" …" if len(missing) > 10 else "")
            )
        extras = {n for n in valid_names if n and n not in pasted_assets
                  and n != "(unknown)"} - pasted_assets
        if len(extras) > len(valid_names) * 0.5:
            inconsistencies.append(
                f"Output contains {len(extras)} names absent from paste — "
                "verify they're real source rows, not synthetic."
            )

    sys.stdout.write("\nInconsistencies detected:\n")
    if not inconsistencies:
        sys.stdout.write("  (none)\n")
    for inc in inconsistencies:
        sys.stdout.write(f"  - {inc}\n")

    if state.get("issue_url") and inconsistencies:
        body = "## Cross-check inconsistencies\n\n" + "\n".join(f"- {x}" for x in inconsistencies)
        github.comment_on_issue(state["issue_url"], body)

    return {"cross_check_paste": paste, "inconsistencies": inconsistencies}


def write_parquet(state: State) -> State:
    records = state.get("valid", [])
    out = state.get("out_path") or (
        finalize_mod.company_dir(state["company"]) / f"{state['company'].lower()}_pipeline.parquet"
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = out.with_name(f"{out.stem}_{ts}{out.suffix}")
    try:
        import polars as pl
        pl.DataFrame(records).write_parquet(str(out))
        written = str(out)
    except Exception as exc:  # noqa: BLE001
        fallback = out.with_suffix(".json")
        fallback.write_text(json.dumps(records, indent=2, default=str))
        written = str(fallback)
        state.setdefault("errors", []).append(f"parquet failed ({exc}); wrote {fallback}")
    return {"parquet_path": written, "out_path": written}


def finalize(state: State) -> State:
    log_path = finalize_mod.write_log_md(
        state["company"],
        source_url=state.get("source", ""),
        tier_label=state.get("tier_label", "Unknown"),
        tier_actual=state.get("tier_actual", "Unknown"),
        source_choice=state.get("source_choice") or "unknown",
        probe_results=state.get("probe_results", {}),
        field_mapping=state.get("field_mapping", {}),
        parquet_path=state.get("parquet_path", ""),
        inconsistencies=state.get("inconsistencies", []),
    )
    rel_log = log_path.relative_to(finalize_mod._PROJECT_ROOT).as_posix()
    finalize_mod.mark_done(state["company"], rel_log)

    if state.get("issue_url"):
        body = (
            f"## Extraction complete\n\n"
            f"- Parquet: `{state.get('parquet_path', 'n/a')}`\n"
            f"- log.md: `{rel_log}`\n"
            f"- Tier: {state.get('tier_actual')} (was {state.get('tier_label')})\n"
            f"- Inconsistencies: {len(state.get('inconsistencies', []))}\n"
        )
        github.close_issue(state["issue_url"], comment=body)

    return {"log_md_path": str(log_path)}


# --- Build ----------------------------------------------------------------
def build():
    g = StateGraph(State)
    g.add_node("load_sources_md", load_sources_md)
    g.add_node("create_github_issue", create_github_issue)
    g.add_node("probe_sources", probe_sources)
    g.add_node("classify_tier", classify_tier)
    g.add_node("present_sources_and_confirm", present_sources_and_confirm)
    g.add_node("ingest_raw", ingest_raw)
    g.add_node("confirm_field_mapping", confirm_field_mapping)
    g.add_node("map_and_validate", map_and_validate)
    g.add_node("manual_cross_check", manual_cross_check)
    g.add_node("write_parquet", write_parquet)
    g.add_node("finalize", finalize)

    g.add_edge(START, "load_sources_md")
    g.add_edge("load_sources_md", "create_github_issue")
    g.add_edge("create_github_issue", "probe_sources")
    g.add_edge("probe_sources", "classify_tier")
    g.add_edge("classify_tier", "present_sources_and_confirm")
    g.add_edge("present_sources_and_confirm", "ingest_raw")
    g.add_edge("ingest_raw", "confirm_field_mapping")
    g.add_edge("confirm_field_mapping", "map_and_validate")
    g.add_edge("map_and_validate", "manual_cross_check")
    g.add_edge("manual_cross_check", "write_parquet")
    g.add_edge("write_parquet", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


# --- CLI ------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Pharma extraction LangGraph flow (replaces the manual "
                    "extraction prompt with a structured state machine).",
    )
    p.add_argument("--company", required=True,
                   help="company slug as listed in docs/sources.md, e.g. 'abbvie'")
    p.add_argument("--source", default=None,
                   help="override the source URL from docs/sources.md")
    p.add_argument("--model", default="anthropic/claude-sonnet-4-5",
                   help="opencode model id (unused in this build — kept "
                        "for forward compatibility)")
    p.add_argument("--output", default=None,
                   help="parquet output path (defaults to "
                        "src/pharmas/<company>/<company>_pipeline.parquet)")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--no-issue", action="store_true",
                   help="skip GitHub issue creation/commenting")
    args = p.parse_args(argv)

    if args.no_issue:
        github.gh_available = lambda: False  # type: ignore[assignment]

    init: State = {
        "company": args.company,
        "model": args.model,
        "out_path": args.output
            or str(finalize_mod.company_dir(args.company)
                   / f"{args.company.lower()}_pipeline.parquet"),
        "max_retries": args.max_retries,
        "retry_count": 0,
        "errors": [],
        "field_mapping": {},
    }
    if args.source:
        init["source"] = args.source

    final = build().invoke(init)

    sys.stdout.write("\n=== DONE ===\n")
    sys.stdout.write(f"  parquet : {final.get('parquet_path', '?')}\n")
    sys.stdout.write(f"  log.md  : {final.get('log_md_path', '?')}\n")
    sys.stdout.write(f"  issue   : {final.get('issue_url') or '(skipped)'}\n")
    sys.stdout.write(f"  valid   : {len(final.get('valid', []))}\n")
    sys.stdout.write(f"  invalid : {len(final.get('invalid', []))}\n")
    if final.get("inconsistencies"):
        sys.stdout.write("  inconsistencies:\n")
        for inc in final["inconsistencies"]:
            sys.stdout.write(f"    - {inc}\n")
    for e in final.get("errors", []):
        sys.stdout.write(f"  ! {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())