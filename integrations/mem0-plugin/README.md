# Mem0 Plugin for Claude Code, Claude Cowork, Cursor, Codex, OpenCode & Antigravity

Add persistent memory to your AI workflows. Store, retrieve, and manage memories across sessions using the Mem0 Platform. Works with **Claude Code** (CLI), **Claude Cowork** (desktop app), **Cursor**, **Codex**, **OpenCode**, and **Antigravity**.

## Quick path for agents

If you're an AI agent setting up Mem0 autonomously (no human dashboard signup available), run:

```bash
mem0 init --agent --json
```

This mints an evaluation API key in <5 seconds — no email, no OTP, no browser. The key is written to your config and exported as `MEM0_API_KEY` for the current shell. Use it immediately against the Mem0 Platform or the MCP server. The human owner can later run `mem0 init --email <their-email>` to claim ownership: memories transfer, the same API key keeps working, and the agent isn't disrupted.

Humans setting up Mem0 by hand should continue with Step 1 below.

## Step 1: Set your API key

> **You must complete this step before installing the plugin.**

1. Sign up at [app.mem0.ai](https://app.mem0.ai?utm_source=oss&utm_medium=mem0-plugin-readme) if you haven't already
2. Go to [app.mem0.ai/dashboard/api-keys](https://app.mem0.ai/dashboard/api-keys?utm_source=oss&utm_medium=mem0-plugin-readme)
3. Click **Create API Key** and copy the key (starts with `m0-`)
4. Set the key using **one** of these methods:

   **CLI** — add to your shell profile:

   ```bash
   # For zsh (default on macOS)
   echo 'export MEM0_API_KEY="m0-your-api-key"' >> ~/.zshrc
   source ~/.zshrc

   # For bash
   echo 'export MEM0_API_KEY="m0-your-api-key"' >> ~/.bashrc
   source ~/.bashrc
   ```

   **Desktop app** — use the local environment editor:

   Click the environment dropdown next to the prompt box → hover over **Local** → click the **gear icon** → add `MEM0_API_KEY` with your key. Values are stored encrypted on your machine.

   > **Note:** The Desktop app does not inherit custom environment variables from shell profiles — it only reads `PATH`. You must use the local environment editor for Desktop.

5. Confirm it's set:

   ```bash
   echo $MEM0_API_KEY
   # Should print: m0-your-api-key
   ```

## Step 2: Install the plugin

Choose one of the options below. All require `MEM0_API_KEY` to be set first (see above).

### Claude Code (CLI) / Claude Cowork (Desktop)

Claude Code and Claude Cowork share the same plugin system.

**CLI:**

```
/plugin marketplace add mem0ai/mem0
/plugin install mem0@mem0-plugins
```

**Cowork desktop app:** Open the Cowork tab, click **Customize** in the sidebar, click **Browse plugins**, and install Mem0.

This installs the full plugin including the MCP server, lifecycle hooks (automatic memory capture), and the Mem0 SDK skill.

### Codex

Codex support defaults to the self-hosted setup in this repository:

```bash
export MEM0_HOST="http://localhost:8888"      # Mem0 REST API
export MEM0_API_KEY="your-admin-or-user-key" # matches your self-hosted server
```

Run the local MCP bridge (`mem0-mcp`) on `localhost:9003` with Streamable HTTP enabled. In the bundled Docker Compose setup this is the `mem0-mcp` service, and Codex connects to `http://localhost:9003/mcp`.

**Option A — Direct MCP** (fastest, MCP only):

Codex reads MCP servers from `~/.codex/config.toml` as TOML. Add:

```toml
[mcp_servers.mem0]
url = "http://localhost:9003/mcp"
bearer_token_env_var = "MEM0_API_KEY"
```

Export `MEM0_API_KEY` in your shell and restart Codex. `codex mcp add` only supports stdio servers, so HTTP servers like Mem0's must be added via `config.toml` directly (or via the **Plugins → Connect to a custom MCP → Streamable HTTP** UI in the Codex app).

> **Don't combine Direct MCP with the full plugin.** The plugin manifest auto-registers `mem0` as an MCP server via `integrations/mem0-plugin/.codex-mcp.json`; adding a manual `[mcp_servers.mem0]` block would duplicate the registration.

**Option B — Sideload the plugin** (full experience: MCP + skills + opt-in hooks):

Register this repository as a local marketplace:

```bash
codex plugin marketplace add /home/hx/AI/Ext/mem0
```

This points Codex at the repo's `.agents/plugins/marketplace.json`, which references `integrations/mem0-plugin/` as the local source. Restart Codex, run `/plugins`, and install **Mem0** from the **Mem0 Plugins** marketplace.

The bundled Codex MCP template (`.codex-mcp.json`) defaults to `http://localhost:9003/mcp`. To switch this plugin back to the hosted platform, copy `.codex-mcp.hosted.json` over `.codex-mcp.json` or run the hook installer with `--hosted`.

**Optional — enable lifecycle hooks.** Codex doesn't auto-wire hooks from plugin manifests; it only reads `~/.codex/hooks.json` (or `<repo>/.codex/hooks.json`) ([docs](https://developers.openai.com/codex/hooks)). Run the bundled installer once to merge Mem0's entries:

```bash
python3 /home/hx/AI/Ext/mem0/integrations/mem0-plugin/scripts/install_codex_hooks.py
```

When `MEM0_HOST` is set, the installer uses self-hosted mode by default: hook script URLs point at `$MEM0_HOST`, and `.codex-mcp.local.json` is copied to `.codex-mcp.json`. This merges Mem0 entries into `~/.codex/hooks.json` with absolute paths pointing into your clone:

| Event | What it does |
|-------|--------------|
| `SessionStart` | Loads prior memories as bootstrap context |
| `UserPromptSubmit` | Injects relevant memories into the prompt |
| `Stop` | Reminds the agent to persist learnings at turn end |

Re-running the installer is idempotent (replaces the Mem0 entries rather than duplicating) and preserves any other hooks you have. To remove: `python3 .../install_codex_hooks.py --uninstall`. If you move or delete the clone directory, re-run the installer from the new location — the hooks file stores absolute paths.

**Switching modes:** Run `python3 .../install_codex_hooks.py --hosted` to use `https://api.mem0.ai` and copy `.codex-mcp.hosted.json` into place. Run `python3 .../install_codex_hooks.py --self-hosted --host http://localhost:8888` to force a self-hosted URL.

Codex hooks also require the `hooks` feature flag in `~/.codex/config.toml` (older builds used `codex_hooks`, which now emits a deprecation warning):

```toml
[features]
hooks = true
```

The installer prints a reminder if the flag isn't set. Restart Codex after editing the config.

**Managing the plugin:**

```bash
codex plugin marketplace upgrade               # pull latest plugin versions
codex plugin marketplace remove mem0-plugins   # unregister the marketplace
```

### Cursor

> **Already have `mem0` configured as an MCP server?** Remove the existing entry from your Cursor MCP settings before installing to avoid duplicate tools.

**Option A — One-click deeplink** (installs MCP server only):

[Install Mem0 MCP in Cursor](cursor://anysphere.cursor-deeplink/mcp/install?name=mem0&config=eyJtY3BTZXJ2ZXJzIjp7Im1lbTAiOnsidXJsIjoiaHR0cHM6Ly9tY3AubWVtMC5haS9tY3AvIiwiaGVhZGVycyI6eyJBdXRob3JpemF0aW9uIjoiVG9rZW4gJHtlbnY6TUVNMF9BUElfS0VZfSJ9fX19)

**Option B — Manual configuration** (MCP server only):

Add the following to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mem0": {
      "url": "https://mcp.mem0.ai/mcp/",
      "headers": {
        "Authorization": "Token ${env:MEM0_API_KEY}"
      }
    }
  }
}
```

**Option C — Cursor Marketplace** (full plugin with hooks and skills):

Install from the [Cursor Marketplace](https://cursor.com/marketplace) for the complete experience including lifecycle hooks and the Mem0 SDK skill.

### OpenCode

```bash
opencode plugin @mem0/opencode-plugin
```

Add `--global` to install for all projects. The plugin auto-registers its native memory tools, hooks, and skills via its `config` hook — no MCP server to configure. Restart OpenCode after installing.

See [OpenCode integration docs](https://docs.mem0.ai/integrations/opencode) for full details.

### Antigravity (Google)

**Option A — degit** (recommended):

```bash
# Install the plugin (MCP server, hooks, scripts)
npx degit mem0ai/mem0/integrations/mem0-plugin ~/.gemini/config/plugins/mem0
```

This installs the MCP server, lifecycle hooks, and shared scripts.

See [Antigravity integration docs](https://docs.mem0.ai/integrations/antigravity) for full details.

## Post-Installation: Run `/mem0:onboard`

After installing, start a new session and run:

```
/mem0:onboard
```

This runs the setup wizard which:
1. Verifies your API key and MCP connection
2. Detects and imports project files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`)
3. Installs coding-optimized memory categories
4. Shows your identity (user ID, project scope, branch)

The onboarding is idempotent — safe to re-run anytime. On first session in a new project (0 memories), Claude is prompted to run it automatically.

## Verify it works

After onboarding, confirm everything is connected:

1. Run `/mem0:health` to check connectivity
2. Run `/mem0:stats` to see memory counts
3. Try `/mem0:remember "we use TypeScript"` then `/mem0:tour` to see it stored

## Available Skills

The plugin includes 17 skills accessible via `/mem0:` commands:

| Command | Description |
|---------|-------------|
| `/mem0:remember` | Store a memory verbatim — decisions, preferences, conventions |
| `/mem0:tour` | Browse all memories grouped by category |
| `/mem0:peek` | Quick search with compact one-liner results |
| `/mem0:stats` | Session and project memory statistics |
| `/mem0:dream` | Consolidate memories — merge duplicates, resolve contradictions |
| `/mem0:pin` | Protect critical memories from pruning |
| `/mem0:forget` | Delete memories by search or ID |
| `/mem0:health` | Diagnose connectivity, API key, and read/write |
| `/mem0:export` | Export memories to portable Markdown |
| `/mem0:import` | Import memories from export file or MEMORY.md |
| `/mem0:list-projects` | List all projects with stored memories |
| `/mem0:switch-project` | Override auto-detected project scope |
| `/mem0:memory-reviewer` | Audit memory quality — duplicates, contradictions, stale |
| `/mem0:context-loader` | Pre-load relevant memories for current task |

## What's included

| Component | Claude Code / Cowork | Cursor (Marketplace) | Cursor (Deeplink/Manual) | Codex (Sideload) | Codex (Direct MCP) | OpenCode (Full) | OpenCode (MCP) | Antigravity |
|-----------|:--------------------:|:--------------------:|:------------------------:|:----------------:|:------------------:|:---------------:|:--------------:|:-----------:|
| MCP Server | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Lifecycle Hooks | Yes | Yes | No | Opt-in | No | Yes | No | Yes |
| Mem0 SDK Skill | Yes | Yes | No | Yes | No | Yes | No | Yes |

- **MCP Server** — Connects to the Mem0 remote MCP server (`mcp.mem0.ai`), providing tools to add, search, update, and delete memories. No local dependencies required.
- **Lifecycle Hooks** — Automatic memory capture at key points. Claude Code, Cursor, OpenCode, and Antigravity wire hooks natively when the full plugin is installed. Codex hooks are opt-in via a one-time installer (`scripts/install_codex_hooks.py`).
- **Mem0 SDK Skill** — Guides the AI on how to integrate the Mem0 SDK (Python & TypeScript) into your applications.

## Updating the plugin

When the plugin updates (new version pulled from the marketplace, or a fresh local install), the MCP server connection in your existing session is left holding a stale handle and stops responding. **Restart your client to reconnect:**

- **Claude Code:** run `/restart` in the prompt, or close and reopen the CLI.
- **Cursor:** quit and relaunch.
- **Codex:** restart the editor session.
- **OpenCode:** restart the session.
- **Antigravity:** restart the session.

Your `MEM0_API_KEY` doesn't need to be re-entered — the auth header is re-read from your environment on the new session. The plugin's MCP config uses `${MEM0_API_KEY}` interpolation at session start, not at install time, so as long as the env var is set persistently (in your shell profile or `~/.claude/settings.json` `env` block), reconnection is automatic on restart.

If reconnection still fails after a restart, check that `MEM0_API_KEY` is reachable in the new shell (`echo $MEM0_API_KEY`) and confirm you're using a key that starts with `m0-` (from https://app.mem0.ai/dashboard/api-keys, not a legacy token).

## Coding-tuned categories (automatic)

mem0 auto-tags every memory with one or more `categories` from a project-level list. The default list is consumer-oriented (`food`, `hobbies`, `music` …) — useful for chat assistants, less so for code. **The plugin installs a coding-focused taxonomy automatically in the background on session start** — no prompt, no manual step. New memories then auto-tag against 17 development-oriented categories: `architecture_decisions`, `anti_patterns`, `task_learnings`, `tooling_setup`, `bug_fixes`, `coding_conventions`, `user_preferences`, `dependency_decisions`, `performance_findings`, `security_constraints`, `testing_patterns`, `data_model`, `api_contracts`, `deployment_runbook`, `team_norms`, `domain_glossary`, `experiment_results`.

The background setup is idempotent and runs once per account (cached in `~/.mem0/categories_setup.json`); it re-applies only if the taxonomy itself changes. To preview the taxonomy or force a refresh manually:

```bash
# Dry-run -- prints current vs proposed, no changes:
python integrations/mem0-plugin/scripts/setup_coding_categories.py

# Write explicitly:
python integrations/mem0-plugin/scripts/setup_coding_categories.py --apply
```

Requires the `mem0ai` Python SDK (`pip install mem0ai`) and `MEM0_API_KEY` set. `project.update(custom_categories=[...])` always replaces the full list.

## MCP Tools

Once installed, the following tools are available:

| Tool | Description |
|------|-------------|
| `add_memory` | Save text or conversation history for a user/agent |
| `search_memories` | Semantic search across memories with filters |
| `get_memories` | List memories with filters and pagination |
| `get_memory` | Retrieve a specific memory by ID |
| `update_memory` | Overwrite a memory's text by ID |
| `delete_memory` | Delete a single memory by ID |
| `delete_all_memories` | Bulk delete all memories in scope |
| `delete_entities` | Delete a user/agent/app/run entity and its memories |
| `list_entities` | List users/agents/apps/runs stored in Mem0 |

## License

Apache-2.0
