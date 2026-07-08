# Approach: Scripted vs Agentic Extraction

## Experiment Design

We'll run **both approaches in parallel on Tier 1 companies** (clean PDFs) to
compare them head-to-head, then apply lessons to harder tiers.

| Approach | Tooling | Who | Tier |
|---|---|---|---|
| Scripted (deterministic) | Python + pdfplumber/Camelot | Anyone (no API key) | Tier 1–2 |
| Agentic (open-loop) | Claude Code / OpenCode CLI | Has API key | Tier 1 (starting) |
| Agentic (framework) | LangGraph / direct API tool-use | Has API key | Tier 3 later |

## Scripted Approach (Deterministic)

- Python scripts per source format (`scripts/tier1/pfizer.py`, etc.)
- pdfplumber for PDF tables, requests for HTML
- LLM (chat interface) writes the code; human reviews + runs it
- Output: JSON matching `data-model.md` schema
- Pros: deterministic, easy to debug, no per-run cost
- Cons: breaks on redesign, new code per source

## Agentic Approach (Open-Loop with CLI)

- Use Claude Code or OpenCode as an agentic subprocess
- Feed it a tightly-scoped task: "extract pipeline from this URL as JSON"
- Harness captures trajectory, validates output, logs failures
- Pros: adapts to layout changes, one prompt for many sources
- Cons: stochastic, harder to debug, needs API key + per-run cost

## Agentic Framework Exploration

Later we'll compare Claude Code CLI vs a proper framework:

- **[LangGraph](https://langchain-ai.github.io/langgraph/)** — state-machine
  orchestration, multi-agent, built-in persistence
- **Direct Anthropic API + tool use** — simplest, most control
- **CrewAI / AutoGen** — higher-level abstractions

Evaluation axis: setup time, debugging ease, reliability, cost.

## What Each Team Member Can Do

| Access | Can work on |
|---|---|
| API key | Agentic streams (CLI or framework), harness infrastructure |
| No API key | Scripted Python parsers, validation logic, schema design |
| Chat-only Claude | Code generation for scripted parsers, documentation |