#!/usr/bin/env bash
# redirect_mcp.sh — point the mem0-plugin's bundled MCP config at the local
# self-hosted mem0-mcp HTTP/SSE server instead of https://mcp.mem0.ai/mcp/.
#
# Background: the @mem0/mem0-plugins package ships TWO MCP config files
#   - .mcp.json          (Claude Code's standard format)
#   - mcp_config.json    (legacy format kept for backwards compat)
# Both hardcode the hosted mcp.mem0.ai endpoint. We rewrite both to an SSE
# entry pointing at the mem0-mcp container exposed by docker-compose on
# http://localhost:9003/sse (combined transport: SSE for Claude Code,
# Streamable HTTP /mcp for Codex).
#
# Idempotent. Backs up to .self-mem0.bak on first run. Re-run after each
# plugin upgrade (it auto-targets the highest installed version).
#
# Usage:
#   self-mem0/plugins/redirect_mcp.sh             # rewrite to local SSE
#   self-mem0/plugins/redirect_mcp.sh /custom     # custom plugin version dir
#   self-mem0/plugins/redirect_mcp.sh --revert    # restore upstream .mcp.json

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# The mem0-mcp container (built from ../mem0-mcp) listens on 9003 and serves
# SSE at /sse + Streamable HTTP at /mcp. Override MEM0_MCP_URL for non-default
# ports or remote hosts.
MEM0_MCP_URL="${MEM0_MCP_URL:-http://localhost:9003/sse}"

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

if [ -z "${MEM0_API_KEY:-}" ]; then
  echo "  WARNING: MEM0_API_KEY is not set in the current shell." >&2
  echo "  Add to your shell profile (~/.bashrc or ~/.zshrc):" >&2
  echo "    export MEM0_API_KEY=\"\$(grep ADMIN_API_KEY $(cd "$ROOT/.." && pwd)/server/.env | sed 's/.*=//' | tr -d '\"')\"" >&2
  echo "  Claude Code sends it as the Bearer token to the local MCP server." >&2
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
      "type": "sse",
      "url": "$MEM0_MCP_URL",
      "headers": {
        "Authorization": "Bearer \${MEM0_API_KEY}"
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
echo "verify with: claude mcp list  (expect: mem0 → $MEM0_MCP_URL (sse) ✓ Connected)"
