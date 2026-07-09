"""Human-in-the-loop gates — pause the graph and read stdin for decisions.

Each gate renders a numbered prompt to stdout (with default-option numbers
the user can type), reads one line, and returns the parsed answer in state.

The graph itself does NOT use LangGraph's `interrupt` — it relies on the
node's stdin read blocking execution naturally, which is simpler and works
identically when the flow is invoked from a script or a notebook.
"""

from __future__ import annotations

import sys
from typing import Any


def _print_and_read(question: str, default: str | None = None) -> str:
    sys.stdout.write(question)
    if default is not None:
        sys.stdout.write(f" [{default}]")
    sys.stdout.write("\n> ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError("stdin closed before gate answered")
    answer = line.rstrip("\n").strip()
    return answer or default or ""


def ask_choice(question: str, options: list[str],
               default_index: int = 0) -> str:
    """Print numbered options and read a choice. Returns the chosen option
    (the original string, not the number). Accepts either the number or
    the option text itself."""
    sys.stdout.write(question + "\n")
    for i, opt in enumerate(options):
        marker = " (default)" if i == default_index else ""
        sys.stdout.write(f"  {i + 1}. {opt}{marker}\n")
    raw = _print_and_read(f"choose 1-{len(options)} (or option text)",
                          default=str(default_index + 1))
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
        idx = default_index
        return options[idx]
    for opt in options:
        if raw.strip().lower() == opt.lower():
            return opt
    return options[default_index]


def ask_batched(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask up to N short-answer questions in one batch (per
    instruction_for_agent.md: 'batch up to 4 at once').

    Each question dict:
        {"key": str, "prompt": str, "choices": list[str] | None,
         "default": str | None, "allow_other": bool}

    Returns {key: answer} for every question.
    """
    sys.stdout.write(f"\n--- {len(questions)} mapping question(s) ---\n")
    answers: dict[str, Any] = {}
    for i, q in enumerate(questions, start=1):
        sys.stdout.write(f"\nQ{i}. {q['prompt']}\n")
        choices = q.get("choices")
        if choices:
            for j, c in enumerate(choices):
                marker = " (default)" if j == q.get("default_index", 0) else ""
                sys.stdout.write(f"  {j + 1}. {c}{marker}\n")
            raw = _print_and_read(
                f"choose 1-{len(choices)} or type your own",
                default=str(q.get("default_index", 0) + 1),
            )
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(choices):
                    answers[q["key"]] = choices[idx]
                    continue
            except ValueError:
                pass
            answers[q["key"]] = raw
        else:
            answers[q["key"]] = _print_and_read(
                q.get("placeholder", ""),
                default=q.get("default"),
            )
    sys.stdout.write("--- end of questions ---\n\n")
    return answers


def ask_free_text(prompt: str) -> str:
    """Read multi-line input until a sentinel line ('---') or EOF."""
    sys.stdout.write(prompt + "\n")
    sys.stdout.write("(paste freely; finish with a line containing only '---')\n")
    lines: list[str] = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        if line.rstrip("\n").rstrip() == "---":
            break
        lines.append(line.rstrip("\n"))
    return "\n".join(lines)


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = _print_and_read(f"{prompt} {suffix}",
                          default="y" if default else "n")
    return raw.lower().startswith("y") if raw else default