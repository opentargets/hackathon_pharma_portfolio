---
title: Setup
nav_order: 3
---

# Setup & Dependencies

## Claude Code

Already configured for team members who have access. No additional setup needed.

## OpenCode (Recommended)

OpenCode is the open-source AI coding agent we'll use for the agentic extraction approach.

### Installation

```bash
# macOS (Homebrew)
brew install anomalyco/tap/opencode

# Or via install script (any platform)
curl -fsSL https://opencode.ai/install | bash

# Or via npm
npm install -g opencode-ai
```

### Configure a Model (OpenCode Zen)

OpenCode Zen provides curated, tested models. We recommend starting with the **free** model.

1. Run the `/connect` command in the OpenCode TUI, select **OpenCode Zen**:
   ```
   /connect
   ```
2. Your browser will open to `opencode.ai/auth` — sign in, add billing details (not required for free models), and copy your API key.
3. Paste the key in the terminal.
4. Set the free model in your project's `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/deepseek-v4-flash-free"
}
```

> **DeepSeek V4 Flash Free** is available at no cost through OpenCode Zen. Input, output, and cached reads are all free. Data collected during the free period may be used to improve the model — avoid submitting confidential information.

You can switch to a paid model anytime by running `/models` in the TUI.

### Verify Installation

```bash
opencode --version
```

Should print `1.17.13` or later.

## Python Dependencies (Scripted Approach)

For the deterministic PDF/HTML parsing stream, install via `uv` or `pip`:

```bash
uv pip install pdfplumber requests beautifulsoup4 lxml
```

Optional for chart-style PDFs (Tier 2):

```bash
uv pip install pytesseract pdf2image
```

## API Keys (Agentic Framework Approach)

For the LangGraph / direct API agentic stream, you'll need an API key from one of:

- **Anthropic** — `ANTHROPIC_API_KEY` (Claude Sonnet 4.6, etc.)
- **OpenAI** — `OPENAI_API_KEY` (GPT-5.3 Codex, etc.)
- **OpenCode Zen** — `OPENCODE_API_KEY` (also usable via direct API at `https://opencode.ai/zen/v1/...`)

Set them as environment variables or in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Summary

| Team member | Has what? | Can work on |
|---|---|---|
| Has API key | Anthropic / OpenAI / Zen key | Agentic streams (LangGraph, direct API), harness |
| Has OpenCode + Zen free model | `opencode/deepseek-v4-flash-free` | Agentic extraction via OpenCode CLI |
| No API key | Python + libraries | Scripted PDF parsers (Tier 1–2), validation, schema |
