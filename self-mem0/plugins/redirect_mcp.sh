#!/usr/bin/env bash
# redirect_mcp.sh — point the mem0-plugin's bundled MCP config at the local
# stdio bridge instead of https://mcp.mem0.ai/mcp/.
#
# Background: the @mem0/mem0-plugins package ships TWO MCP config files
#   - .mcp.json          (Claude Code's standard format)
#   - mcp_config.json    (legacy format kept for backwards compat)
# Both hardcode the hosted mcp.mem0.ai endpoint and there is no env-var
# override. We rewrite both to a stdio entry pointing at the bridge that
# self-mem0/apply.sh installed at self-mem0/mcp_bridge/.venv/bin/mem0-mcp-bridge.
#
# Idempotent. Backs up to .self-mem0.bak on first run. Re-run after each
# plugin upgrade (it auto-targets the highest installed version).
#
# Usage:
#   self-mem0/plugins/redirect_mcp.sh             # rewrite to stdio bridge
#   self-mem0/plugins/redirect_mcp.sh /custom     # custom plugin version dir
#   self-mem0/plugins/redirect_mcp.sh --revert    # restore upstream .mcp.json

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE_BIN="${MEM0_MCP_BRIDGE_BIN:-$ROOT/mcp_bridge/.venv/bin/mem0-mcp-bridge}"
MEM0_HOST_DEFAULT="${MEM0_HOST:-http://localhost:8888}"
# MEM0_USER_ID baked into .mcp.json so it survives shell-less launches
# (IDE, Desktop, etc.). Defaults to a hard-bucketed Claude Code namespace
# under the ubuntu-* scheme so it never collides with other agents.
MEM0_USER_ID_DEFAULT="${MEM0_USER_ID:-ubuntu-claudecode}"

# Per Claude Code docs (code.claude.com/docs/en/mcp), .mcp.json supports
# ${VAR} expansion in env/url/headers/command/args. We use the placeholder
# so the real key stays in the user's shell profile (~/.bashrc) and isn't
# baked into a plugin-managed JSON file. Required precondition:
#     export MEM0_API_KEY="m0sk_..."  in ~/.bashrc (or equivalent)
# Without it, Claude Code fails to parse this .mcp.json at startup.

REVERT=false
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --revert) REVERT=true ;;
    -h|--help) sed -n '1,/^set -e/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done

resolve_target() {
  if [ -n "$TARGET" ]; then
    [ -d "$TARGET" ] || { echo "not a directory: $TARGET" >&2; exit 1; }
    printf '%s' "$TARGET"
    return
  fi
  local base="$HOME/.claude/plugins/cache/mem0-plugins/mem0"
  [ -d "$base" ] || { echo "mem0-plugin not installed under $base" >&2; exit 1; }
  local latest
  latest=$(ls -1 "$base" 2>/dev/null | sort -V | tail -1)
  [ -n "$latest" ] || { echo "no versions under $base" >&2; exit 1; }
  printf '%s/%s' "$base" "$latest"
}

PLUGIN_DIR=$(resolve_target)
echo "→ plugin dir: $PLUGIN_DIR"

restore_one() {
  local f="$1"
  if [ -f "$f.self-mem0.bak" ]; then
    mv -f "$f.self-mem0.bak" "$f"
    echo "  reverted: $f"
  fi
}

if $REVERT; then
  restore_one "$PLUGIN_DIR/.mcp.json"
  restore_one "$PLUGIN_DIR/mcp_config.json"
  echo "done. Restart Claude Code so it re-reads the upstream MCP config."
  exit 0
fi

[ -x "$BRIDGE_BIN" ] || {
  echo "bridge binary not found / not executable: $BRIDGE_BIN" >&2
  echo "run self-mem0/apply.sh first to install the bridge." >&2
  exit 1
}

if [ -z "${MEM0_API_KEY:-}" ]; then
  echo "  WARNING: MEM0_API_KEY is not set in the current shell." >&2
  echo "  Add to your shell profile (~/.bashrc or ~/.zshrc):" >&2
  echo "    export MEM0_API_KEY=\"\$(grep ADMIN_API_KEY $(cd "$ROOT/.." && pwd)/server/.env | sed 's/.*=//' | tr -d '\"')\"" >&2
  echo "  Claude Code requires it to expand \${MEM0_API_KEY} in .mcp.json at startup." >&2
fi

backup_once() {
  local f="$1"
  [ -f "$f.self-mem0.bak" ] || { [ -f "$f" ] && cp -p "$f" "$f.self-mem0.bak"; }
}

write_mcp_json() {
  local f="$1"
  backup_once "$f"
  cat > "$f" <<JSON
{
  "mcpServers": {
    "mem0": {
      "type": "stdio",
      "command": "$BRIDGE_BIN",
      "args": [],
      "env": {
        "MEM0_API_KEY": "\${MEM0_API_KEY}",
        "MEM0_HOST": "$MEM0_HOST_DEFAULT",
        "MEM0_USER_ID": "$MEM0_USER_ID_DEFAULT"
      }
    }
  }
}
JSON
  echo "  rewrote: $f"
}

write_mcp_json "$PLUGIN_DIR/.mcp.json"
write_mcp_json "$PLUGIN_DIR/mcp_config.json"

echo ""
echo "done. Restart Claude Code so it re-reads the MCP config."
echo "verify with: claude mcp list  (expect: mem0 → $BRIDGE_BIN (stdio) ✓ Connected)"
