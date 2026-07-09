
from __future__ import annotations
 
import json
import subprocess
from datetime import date
from enum import Enum
from typing import TypedDict
 
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, ValidationError
 
 
# --- Schema (phase values = Open Targets ClinicalStageCategory) -----------
class Phase(str, Enum):
    WITHDRAWAL = "WITHDRAWAL"; APPROVAL = "APPROVAL"; PHASE_4 = "PHASE_4"
    PREAPPROVAL = "PREAPPROVAL"; PHASE_3 = "PHASE_3"; PHASE_2_3 = "PHASE_2_3"
    PHASE_2 = "PHASE_2"; PHASE_1_2 = "PHASE_1_2"; PHASE_1 = "PHASE_1"
    EARLY_PHASE_1 = "EARLY_PHASE_1"; IND = "IND"; PRECLINICAL = "PRECLINICAL"
    UNKNOWN = "UNKNOWN"
 
 
class PipelineRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    company: str
    asset_name: str
    indication: str
    phase: Phase
    mechanism_of_action: str | None = None
    therapeutic_area: str | None = None
    trial_id: str | None = None
    source_url: str | None = None
    extraction_date: date | None = None
    notes: str | None = None
    phase_from_source: str | None = None
 
 
_PHASE = {
    "preclinical": Phase.PRECLINICAL, "discovery": Phase.PRECLINICAL, "pre-ind": Phase.PRECLINICAL,
    "ind": Phase.IND, "early phase 1": Phase.EARLY_PHASE_1,
    "phase 1": Phase.PHASE_1, "phase i": Phase.PHASE_1, "first-in-human": Phase.PHASE_1, "poc": Phase.PHASE_1,
    "phase 1/2": Phase.PHASE_1_2, "phase i/ii": Phase.PHASE_1_2, "phase 1b/2": Phase.PHASE_1_2,
    "phase 2": Phase.PHASE_2, "phase ii": Phase.PHASE_2, "proof of concept": Phase.PHASE_2,
    "phase 2/3": Phase.PHASE_2_3, "phase ii/iii": Phase.PHASE_2_3,
    "phase 3": Phase.PHASE_3, "phase iii": Phase.PHASE_3, "pivotal": Phase.PHASE_3,
    "phase 4": Phase.PHASE_4,
    "preregistration": Phase.PREAPPROVAL, "nda filed": Phase.PREAPPROVAL,
    "bla filed": Phase.PREAPPROVAL, "submitted": Phase.PREAPPROVAL, "under review": Phase.PREAPPROVAL,
    "registered": Phase.APPROVAL, "approved": Phase.APPROVAL, "marketed": Phase.APPROVAL,
    "discontinued": Phase.WITHDRAWAL, "terminated": Phase.WITHDRAWAL, "suspended": Phase.WITHDRAWAL,
}
_TA = {"oncology": "Oncology", "cancer": "Oncology", "immunology": "Immunology",
       "cardiovascular": "Cardiovascular", "neuroscience": "Neuroscience"}
 
 
# --- Graph state ----------------------------------------------------------
class State(TypedDict, total=False):
    company: str
    source: str          # local path or URL of the pipeline source
    model: str           # opencode model id, e.g. "anthropic/claude-sonnet-4-5"
    out_path: str
    raw_rows: list[dict]
    normalized: list[dict]
    valid: list[dict]
    invalid: list[tuple]  # (asset_name, [pydantic errors])
    retry_count: int
    max_retries: int
    errors: list[str]

def _extract_json_array(raw: str, errors: list) -> list[dict]:
    """Pull the first top-level JSON array out of the model's output, even if
    it's wrapped in prose or ```json fences."""
    # Prefer a fenced block if present.
    if "```" in raw:
        import re
        m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    # Otherwise grab from the first '[' to the last ']'.
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
 
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", state["model"], prompt],
            capture_output=True, text=True, timeout=600,
        )
    except FileNotFoundError:
        return {"raw_rows": [], "retry_count": retry, "invalid": [],
                "errors": errors + ["opencode not found on PATH — is it installed?"]}
    except subprocess.TimeoutExpired:
        return {"raw_rows": [], "retry_count": retry, "invalid": [],
                "errors": errors + ["opencode timed out after 600s"]}
 
    if result.returncode != 0:
        errors.append(f"opencode exited {result.returncode}: {result.stderr[:300]}")
        return {"raw_rows": [], "retry_count": retry, "invalid": [], "errors": errors}
 
    rows = _extract_json_array(result.stdout, errors)
    # Clear `invalid` so the router re-reads a fresh split from validate().
    return {"raw_rows": rows, "retry_count": retry, "invalid": [], "errors": errors}
 
 

def normalize(state: State) -> State:
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
                "phase": _PHASE.get((raw_phase or "").strip().lower(), Phase.UNKNOWN).value,
                "phase_from_source": raw_phase,
                "therapeutic_area": _TA.get((ta or "").strip().lower(), ta.title() if ta else None),
                "source_url": row.get("source_url", state.get("source")),
                "extraction_date": date.today().isoformat(),
            })
    return {"normalized": out}
 
 
def validate(state: State) -> State:
    valid, invalid = [], []
    for row in state.get("normalized", []):
        try:
            valid.append(PipelineRecord.model_validate(row).model_dump(mode="json"))
        except ValidationError as e:
            invalid.append((row.get("asset_name", "?"), e.errors()))
    return {"valid": valid, "invalid": invalid}
 
 
def route(state: State) -> str:
    """The agentic control point: retry the inner agent, or finish."""
    if state.get("invalid") and state.get("retry_count", 0) < state.get("max_retries", 2):
        return "opencode_extract"
    return "write"
 
 
def write(state: State) -> State:
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
    return {"out_path": written}
 
 
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
    args = p.parse_args()
 
    final = build().invoke({
        "company": args.company,
        "source": args.source,
        "model": args.model,
        "out_path": args.output or f"{args.company.lower()}.parquet",
        "retry_count": 0,
        "max_retries": args.max_retries,
    })
 
    print(f"[{args.company}] {len(final.get('valid', []))} valid "
          f"(after {final.get('retry_count', 0)} retr{'y' if final.get('retry_count')==1 else 'ies'}) "
          f"-> {final.get('out_path')}")
    for asset, errs in final.get("invalid", []):
        print(f"  ! still invalid: {asset}: {errs}")
    for e in final.get("errors", []):
        print(f"  ! {e}")