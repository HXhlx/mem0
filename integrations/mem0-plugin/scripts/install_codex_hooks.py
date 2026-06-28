#!/usr/bin/env python3
"""Install Mem0 lifecycle hooks into ~/.codex/hooks.json.

Codex discovers hooks only at ~/.codex/hooks.json or <repo>/.codex/hooks.json,
and has no plugin-host mechanism for auto-wiring hooks from an installed
plugin. This installer reads the template at hooks/codex-hooks.json, rewrites
the ${PLUGIN_ROOT} placeholder to the absolute install path of this
plugin, then merges the entries into ~/.codex/hooks.json.

Re-running is idempotent: existing Mem0 entries (identified by the plugin
directory name in the command string) are removed before fresh entries are
added, so upgrades don't leave duplicates.

Usage:
  python3 install_codex_hooks.py                          # install or update
  python3 install_codex_hooks.py --uninstall               # remove Mem0 entries
  python3 install_codex_hooks.py --self-hosted             # use local Mem0 server
  python3 install_codex_hooks.py --self-hosted --host http://myhost:8888
  python3 install_codex_hooks.py --hosted                  # use hosted Mem0

After installing, Codex requires the hooks feature flag in ~/.codex/config.toml:

  [features]
  hooks = true
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent

CODEX_DIR = Path.home() / ".codex"
HOOKS_FILE = CODEX_DIR / "hooks.json"
CONFIG_FILE = CODEX_DIR / "config.toml"

TEMPLATE_FILE = PLUGIN_ROOT / "hooks" / "codex-hooks.json"
CODEX_MCP_FILE = PLUGIN_ROOT / ".codex-mcp.json"
CODEX_MCP_LOCAL_FILE = PLUGIN_ROOT / ".codex-mcp.local.json"
CODEX_MCP_HOSTED_FILE = PLUGIN_ROOT / ".codex-mcp.hosted.json"

# Substring we look for when identifying entries this installer owns.
# Matches the plugin directory name, which stays stable across install paths.
OWNER_MARKER = "mem0-plugin"
SELF_HOSTED_MARKER = "MEM0_HOST"
HOSTED_API_URL = "https://api.mem0.ai"


def load_template() -> dict:
    raw = TEMPLATE_FILE.read_text().replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT))
    template = json.loads(raw)

    # Inject identity env vars into every hook command so the hook runner
    # sees them. Codex's shell_environment_policy only applies to Bash tool
    # calls; lifecycle hooks run in a separate process that does not inherit
    # those vars, so we bake them into the command prefix instead.
    prefix_vars = {}
    for name in ("MEM0_USER_ID", "MEM0_HOST", "MEM0_PROJECT_ID"):
        value = os.environ.get(name, "").strip()
        if value:
            prefix_vars[name] = value
    if prefix_vars:
        prefix = " ".join(f'{k}="{v}"' for k, v in prefix_vars.items()) + " "
        for entries in template.get("hooks", {}).values():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    if cmd:
                        hook["command"] = prefix + cmd
    return template


def load_existing() -> dict:
    if not HOOKS_FILE.exists():
        return {"hooks": {}}
    try:
        return json.loads(HOOKS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"error: failed to read {HOOKS_FILE}: {e}", file=sys.stderr)
        sys.exit(1)


def is_owned_entry(entry: dict) -> bool:
    for hook in entry.get("hooks", []):
        if OWNER_MARKER in hook.get("command", ""):
            return True
    return False


def strip_owned_entries(config: dict) -> dict:
    hooks = config.get("hooks", {}) or {}
    for event in list(hooks.keys()):
        hooks[event] = [e for e in hooks[event] if not is_owned_entry(e)]
        if not hooks[event]:
            del hooks[event]
    config["hooks"] = hooks
    return config


def merge_template(config: dict, template: dict) -> dict:
    hooks = config.setdefault("hooks", {})
    for event, entries in template.get("hooks", {}).items():
        hooks.setdefault(event, []).extend(entries)
    return config


def write_config(config: dict) -> None:
    CODEX_DIR.mkdir(parents=True, exist_ok=True)
    HOOKS_FILE.write_text(json.dumps(config, indent=2) + "\n")


def feature_flag_enabled() -> bool:
    if not CONFIG_FILE.exists():
        return False
    content = CONFIG_FILE.read_text()
    for line in content.splitlines():
        stripped = line.split("#", 1)[0].strip().replace(" ", "")
        if stripped == "hooks=true":
            return True
    return False


def print_feature_flag_hint() -> None:
    print()
    print("Codex hooks feature flag is not enabled.")
    print(f"Add this to {CONFIG_FILE}:")
    print()
    print("  [features]")
    print("  hooks = true")
    print()
    print("Then restart Codex.")


def _patch_self_hosted(template: dict, host: str) -> dict:
    """Rewrite any hard-coded api.mem0.ai URL in hook commands to *host*."""
    import json as _json

    serialized = _json.dumps(template)
    serialized = serialized.replace(HOSTED_API_URL, host.rstrip("/"))
    return _json.loads(serialized)


def _copy_codex_mcp_template(source: Path) -> None:
    """Copy *source* to .codex-mcp.json, backing up custom contents first."""
    if not source.exists():
        print(f"warning: MCP template not found at {source}", file=sys.stderr)
        return

    if CODEX_MCP_FILE.exists() and CODEX_MCP_FILE.read_text() != source.read_text():
        backup = CODEX_MCP_FILE.with_name(f"{CODEX_MCP_FILE.name}.bak.{int(time.time())}")
        shutil.copy2(CODEX_MCP_FILE, backup)
        print(f"Backed up existing MCP config to {backup}")

    shutil.copy2(source, CODEX_MCP_FILE)
    print(f"Wrote Codex MCP config from {source.name} → {CODEX_MCP_FILE}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or remove Mem0 Codex hooks.")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove Mem0 entries from ~/.codex/hooks.json and exit.",
    )
    parser.add_argument(
        "--self-hosted",
        action="store_true",
        help="Patch hooks to use a local Mem0 server instead of the hosted API.",
    )
    parser.add_argument(
        "--hosted",
        action="store_true",
        help="Use hosted Mem0 API and hosted MCP template even when MEM0_HOST is set.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MEM0_HOST", "http://localhost:8888"),
        help="Self-hosted Mem0 API base URL. Default: $MEM0_HOST or http://localhost:8888.",
    )
    args = parser.parse_args()

    if args.self_hosted and args.hosted:
        parser.error("--self-hosted and --hosted cannot be used together")

    config = load_existing()

    if args.uninstall:
        config = strip_owned_entries(config)
        write_config(config)
        print(f"Removed Mem0 hooks from {HOOKS_FILE}")
        return 0

    # Codex lifecycle hooks register .sh paths directly in ~/.codex/hooks.json.
    # On native Windows .sh has no default handler, so Codex spawning a hook
    # triggers "Open With" dialogs (one OpenWith.exe per event). See #5243.
    if platform.system() == "Windows":
        print(
            "Codex lifecycle hooks register .sh scripts directly, which Windows\n"
            "cannot execute without a bash interpreter on PATH. Re-run this\n"
            "installer from WSL or Git Bash, or use Mem0 via MCP / Direct tools\n",
            file=sys.stderr,
        )
        return 2

    if not TEMPLATE_FILE.exists():
        print(f"error: template not found at {TEMPLATE_FILE}", file=sys.stderr)
        return 1

    template = load_template()

    use_self_hosted = args.self_hosted or (not args.hosted and bool(os.environ.get("MEM0_HOST")))

    if use_self_hosted:
        api_host = args.host.rstrip("/")
        print(f"Self-hosted mode: patching API URL to {api_host}")
        template = _patch_self_hosted(template, api_host)
        _copy_codex_mcp_template(CODEX_MCP_LOCAL_FILE)
    elif args.hosted:
        print("Hosted mode: using hosted API and MCP server")
        _copy_codex_mcp_template(CODEX_MCP_HOSTED_FILE)

    config = strip_owned_entries(config)
    config = merge_template(config, template)
    write_config(config)

    print(f"Installed Mem0 hooks into {HOOKS_FILE}")
    print(f"Plugin path: {PLUGIN_ROOT}")
    print("Events: PreToolUse, SessionStart, UserPromptSubmit, PostToolUse")

    if not feature_flag_enabled():
        print_feature_flag_hint()

    return 0


if __name__ == "__main__":
    sys.exit(main())
