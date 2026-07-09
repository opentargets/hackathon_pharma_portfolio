---
title: Setup
nav_order: 5
---

# Setup & Dependencies

## Claude Code

Already configured for team members who have access. No additional setup needed.

## OpenCode (Recommended)

OpenCode is the open-source AI coding agent we'll use for the agentic extraction approach.

### Quick Start (Minimal)

```bash
# 1. Install
brew install anomalyco/tap/opencode

# 2. Add an API key (run in the TUI, paste your key)
#    Uses the free DeepSeek V4 Flash Free model via OpenCode Zen
opencode
# then type: /connect → select "OpenCode Zen" → follow browser auth

# 3. Set the model in ~/.config/opencode/opencode.json
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/deepseek-v4-flash-free"
}
```

> **DeepSeek V4 Flash Free** is free through OpenCode Zen. Data during the free period may be used to improve the model — avoid submitting confidential info.

You're done. OpenCode will now pick up the [`AGENTS.md`](../AGENTS.md) in this repo automatically for project-specific context.

### Full Configuration Example

Here is the actual global config used on this project. It shows the model setup, MCP servers (OpenTargets, Context7), agents, and commands:

<details>
<summary><code>~/.config/opencode/opencode.json</code></summary>

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/deepseek-v4-flash-free",
  "plugin": [
    "oh-my-openagent@latest"
  ],
  "agent": {
    "build": {
      "description": "Primary coding and writing agent",
      "mode": "primary",
      "model": "opencode/deepseek-v4-flash-free",
      "tools": {
        "write": true, "edit": true, "bash": true,
        "read": true, "glob": true, "grep": true, "webfetch": true
      }
    }
  },
  "mcp": {
    "opentargets": {
      "type": "remote",
      "url": "https://mcp.platform.opentargets.org/mcp"
    },
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp"
    },
    "filesystem": {
      "type": "local",
      "command": [
        "npx", "-y", "@modelcontextprotocol/server-filesystem",
        "/Users/irenelopez/Documents"
      ]
    }
  },
  "permission": {
    "mcp_*": "ask",
    "opentargets_*": "deny"
  }
}
```

</details>

This project already has an [`AGENTS.md`](../AGENTS.md) at the root — OpenCode reads it automatically on startup, so no project-level `opencode.json` is needed unless you want to override settings.

### Other Installation Methods

```bash
# Install script (any platform)
curl -fsSL https://opencode.ai/install | bash

# npm
npm install -g opencode-ai
```

### Verify

```bash
opencode --version  # should print 1.17.13 or later
```

### oh-my-openagent Plugin (Concurrent Extraction)

[oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) is a plugin that enables multi-agent orchestration for concurrent portfolio extraction. Install it after OpenCode:

```bash
# Install Bun (if not present)
curl -fsSL https://bun.sh/install | bash

# Install oh-my-openagent
bunx oh-my-openagent install --no-tui --platform=opencode --opencode-zen=yes
```

This registers the plugin in `~/.config/opencode/opencode.json` and generates agent configuration in `~/.config/opencode/oh-my-openagent.json`.

Key feature: including the word `ultrawork` (or `ulw`) in any prompt activates the full multi-agent orchestration — useful for running multiple pharma extractions in parallel.

#### Verify the plugin

```bash
bunx oh-my-openagent doctor
```

Expected: no errors (the `ast-grep` warning is benign and doesn't affect extraction).

## Python Dependencies (Scripted Approach)

For the deterministic PDF/HTML parsing stream, install via `uv`:

```bash
uv add pdfplumber requests beautifulsoup4 lxml
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
