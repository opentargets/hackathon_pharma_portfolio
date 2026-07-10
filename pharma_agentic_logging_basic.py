
from __future__ import annotations
 
import json
import subprocess
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TypedDict
 
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, ValidationError
from schema import Phase, PipelineRecord

 
 
_PHASE = {
    "preclinical": Phase.PRECLINICAL,
    "discovery": Phase.PRECLINICAL,
    "pre-ind": Phase.PRECLINICAL,
    "ind": Phase.PHASE_1,
    "early phase 1": Phase.PHASE_1,
    "phase 1": Phase.PHASE_1,
    "phase i": Phase.PHASE_1,
    "first-in-human": Phase.PHASE_1,
    "poc": Phase.PHASE_1,
    "phase 1/2": Phase.PHASE_1_2,
    "phase i/ii": Phase.PHASE_1_2,
    "phase 1b/2": Phase.PHASE_1_2,
    "phase 2": Phase.PHASE_2,
    "phase ii": Phase.PHASE_2,
    "proof of concept": Phase.PHASE_2,
    "phase 2/3": Phase.PHASE_2_3,
    "phase ii/iii": Phase.PHASE_2_3,
    "phase 3": Phase.PHASE_3,
    "phase iii": Phase.PHASE_3,
    "pivotal": Phase.PHASE_3,
    "phase 4": Phase.PHASE_3,
    "preregistration": Phase.PREREGISTRATION,
    "nda filed": Phase.PREREGISTRATION,
    "bla filed": Phase.PREREGISTRATION,
    "submitted": Phase.PREREGISTRATION,
    "under review": Phase.PREREGISTRATION,
    "registered": Phase.REGISTERED,
    "approved": Phase.REGISTERED,
    "marketed": Phase.REGISTERED,
    "discontinued": Phase.DISCONTINUED,
    "terminated": Phase.DISCONTINUED,
    "suspended": Phase.DISCONTINUED,
}


def _normalize_phase(raw_phase: str | None) -> Phase:
    key = (raw_phase or "").strip().lower()
    return _PHASE.get(key, Phase.UNKNOWN)
_TA = {"oncology": "Oncology", "cancer": "Oncology", "immunology": "Immunology",
       "cardiovascular": "Cardiovascular", "neuroscience": "Neuroscience"}
 
 
# --- Graph state ----------------------------------------------------------
class State(TypedDict, total=False):
    company: str
    source: str          # local path or URL of the pipeline source
    model: str           # opencode model id, e.g. "anthropic/claude-sonnet-4-5"
    out_path: str
    log_path: str | None
    raw_rows: list[dict]
    normalized: list[dict]
    valid: list[dict]
    invalid: list[tuple]  # (asset_name, [pydantic errors])
    retry_count: int
    max_retries: int
    errors: list[str]
    trace: list[dict]

def _append_trace(state: State, step: str, status: str, **details) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "status": status,
    }
    if details:
        entry.update(details)
    state.setdefault("trace", []).append(entry)

    log_path = state.get("log_path")
    if log_path:
        _write_trace_log(state, log_path)


def _write_trace_log(state: State, log_path: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Agentic extraction log — {state.get('company', 'unknown')}",
        "",
        f"- Source: {state.get('source', 'n/a')}",
        f"- Model: {state.get('model', 'n/a')}",
        f"- Output: {state.get('out_path', 'n/a')}",
        "",
        "## Execution trace",
        "",
    ]

    for entry in state.get("trace", []):
        lines.append(f"### {entry['step']} — {entry['status']}")
        lines.append(f"- Time: {entry['timestamp']}")
        for key, value in entry.items():
            if key in {"timestamp", "step", "status"}:
                continue
            if isinstance(value, (list, dict)):
                rendered = json.dumps(value, indent=2, default=str)
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _extract_json_array(raw: str, errors: list) -> list[dict]:
    """Pull the first top-level JSON array out of the model's output, even if
    it's wrapped in prose or ```json fences."""
    if "```" in raw:
        import re
        m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        errors.append(f"no JSON array found in output: {raw[:200]}")
        return []
    try:
        rows = json.loads(raw[start : end + 1])
        return rows if isinstance(rows, list) else []
    except json.JSONDecodeError as exc:
        errors.append(f"found brackets but couldn't parse ({exc}): {raw[start:start+200]}")
        return []
 

def opencode_extract(state: State) -> State:
    state = dict(state)
    errors = list(state.get("errors", []))
    retry = state.get("retry_count", 0)
 
    feedback = ""
    if state.get("invalid"):
        retry += 1  # consume one retry from the budget
        details = "\n".join(f"- {asset}: {errs}" for asset, errs in state["invalid"])
        feedback = (
            "\n\nYour previous attempt produced rows that FAILED validation:\n"
            f"{details}\nReturn corrected JSON for the whole pipeline."
        )
 
    prompt = (
        f"Read the {state['company']} investigational pipeline source at "
        f"{state['source']}. Extract every candidate as a JSON array. Each object "
        "has keys: asset_name, mechanism_of_action, therapeutic_area, indication, "
        "phase, trial_id. Use null for anything not stated. Do not infer MoA. Do "
        "not backfill NCT ids. Print ONLY the JSON array to stdout — no prose, no "
        "code fences." + feedback
    )
    _append_trace(state, "opencode_extract", "prompted", prompt_preview=prompt[:400], retry_count=retry)
 
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", state["model"], prompt],
            capture_output=True, text=True, timeout=600,
        )
    except FileNotFoundError:
        _append_trace(state, "opencode_extract", "failed", reason="opencode not found on PATH")
        return {"raw_rows": [], "retry_count": retry, "invalid": [],
                "errors": errors + ["opencode not found on PATH — is it installed?"]}
    except subprocess.TimeoutExpired:
        _append_trace(state, "opencode_extract", "failed", reason="opencode timed out")
        return {"raw_rows": [], "retry_count": retry, "invalid": [],
                "errors": errors + ["opencode timed out after 600s"]}

    if result.returncode != 0:
        errors.append(f"opencode exited {result.returncode}: {result.stderr[:300]}")
        _append_trace(state, "opencode_extract", "failed", reason=f"exit {result.returncode}", stderr=result.stderr[:300])
        return {"raw_rows": [], "retry_count": retry, "invalid": [], "errors": errors}

    rows = _extract_json_array(result.stdout, errors)
    _append_trace(state, "opencode_extract", "completed", rows_found=len(rows), stdout_preview=result.stdout[:400], errors=errors)
    # Clear `invalid` so the router re-reads a fresh split from validate().
    state["raw_rows"] = rows
    state["retry_count"] = retry
    state["invalid"] = []
    state["errors"] = errors
    return state
 

def normalize(state: State) -> State:
    state = dict(state)
    out = []
    for row in state.get("raw_rows", []):
        inds = row.get("indications") or row.get("indication")
        inds = inds if isinstance(inds, (list, tuple)) else [inds]
        for ind in inds:
            raw_phase = row.get("phase") if isinstance(row.get("phase"), str) else None
            ta = row.get("therapeutic_area")
            out.append({
                **{k: v for k, v in row.items() if k != "indications"},
                "company": row.get("company", state["company"]),
                "indication": ind,
                "phase": _normalize_phase(raw_phase).value,
                "phase_from_source": raw_phase,
                "therapeutic_area": _TA.get((ta or "").strip().lower(), ta.title() if ta else None),
                "source_url": row.get("source_url", state.get("source")),
                "extraction_date": date.today().isoformat(),
            })
    state["normalized"] = out
    _append_trace(state, "normalize", "completed", rows_normalized=len(out))
    return state
 
 
def validate(state: State) -> State:
    state = dict(state)
    valid, invalid = [], []
    for row in state.get("normalized", []):
        try:
            valid.append(PipelineRecord.model_validate(row).model_dump(mode="json"))
        except ValidationError as e:
            invalid.append((row.get("asset_name", "?"), e.errors()))
    state["valid"] = valid
    state["invalid"] = invalid
    _append_trace(state, "validate", "completed", valid_rows=len(valid), invalid_rows=len(invalid))
    return state
 
 
def route(state: State) -> str:
    """The agentic control point: retry the inner agent, or finish."""
    invalid = state.get("invalid", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    if invalid and retry_count < max_retries:
        _append_trace(state, "route", "retry", invalid_rows=len(invalid), retry_count=retry_count, max_retries=max_retries)
        return "opencode_extract"
    _append_trace(state, "route", "write", invalid_rows=len(invalid), retry_count=retry_count, max_retries=max_retries)
    return "write"
 
 
def write(state: State) -> State:
    state = dict(state)
    records = state.get("valid", [])
    try:
        import polars as pl
        pl.DataFrame(records).write_parquet(state["out_path"])
        written = state["out_path"]
    except Exception as exc:  # noqa: BLE001 - never let a dep issue lose the data
        fallback = state["out_path"].rsplit(".", 1)[0] + ".json"
        with open(fallback, "w") as fh:
            json.dump(records, fh, indent=2, default=str)
        written = fallback
        state.setdefault("errors", []).append(f"parquet failed ({exc}); wrote {fallback}")
    state["out_path"] = written
    _append_trace(state, "write", "completed", output_path=written, rows_written=len(records))
    return state
 
 
# --- Build the graph ------------------------------------------------------
def build():
    g = StateGraph(State)
    g.add_node("opencode_extract", opencode_extract)
    g.add_node("normalize", normalize)
    g.add_node("validate", validate)
    g.add_node("write", write)
 
    g.add_edge(START, "opencode_extract")
    g.add_edge("opencode_extract", "normalize")
    g.add_edge("normalize", "validate")
    g.add_conditional_edges(
        "validate", route,
        {"opencode_extract": "opencode_extract", "write": "write"},
    )
    g.add_edge("write", END)
    return g.compile()
 
 
if __name__ == "__main__":
    import argparse
 
    p = argparse.ArgumentParser(description="Agentic pharma extraction (LangGraph + OpenCode).")
    p.add_argument("--company", required=True)
    p.add_argument("--source", required=True, help="pipeline PDF path or URL")
    p.add_argument("--model", required=True,
                   help="opencode model id (run `opencode models` to list, "
                        "e.g. anthropic/claude-sonnet-4-5)")
    p.add_argument("--output", default=None)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--log", default=None,
                   help="path to write an execution trace log (Markdown)")
    args = p.parse_args()
 
    log_path = args.log or f"{args.company.lower()}_agent_trace.md"
    final = build().invoke({
        "company": args.company,
        "source": args.source,
        "model": args.model,
        "out_path": args.output or f"{args.company.lower()}.parquet",
        "log_path": log_path,
        "retry_count": 0,
        "max_retries": args.max_retries,
    })

    _append_trace(final, "run_complete", "completed", log_path=log_path, valid_rows=len(final.get("valid", [])))
    _write_trace_log(final, log_path)
 
    print(f"[{args.company}] {len(final.get('valid', []))} valid "
          f"(after {final.get('retry_count', 0)} retr{'y' if final.get('retry_count')==1 else 'ies'}) "
          f"-> {final.get('out_path')}")
    for asset, errs in final.get("invalid", []):
        print(f"  ! still invalid: {asset}: {errs}")
    for e in final.get("errors", []):
        print(f"  ! {e}")