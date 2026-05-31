#!/usr/bin/env bash
# revert.sh — undo what apply.sh did.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"

echo "=== 1. remove docker-compose.override.yaml ==="
rm -f "$REPO/server/docker-compose.override.yaml"

echo "=== 2. remove mcp_bridge venv ==="
rm -rf "$ROOT/mcp_bridge/.venv"

echo "=== 3. revert user-level mem0-plugin patches ==="
if [ -d "$HOME/.claude/plugins/cache/mem0-plugins/mem0" ]; then
  "$ROOT/plugins/patch_mem0_plugin.sh" --revert
  "$ROOT/plugins/redirect_mcp.sh" --revert
fi

echo ""
echo "done. The 12-line hook in server/main.py + server/auth.py remains —"
echo "it's a no-op when self_mem0 isn't on PYTHONPATH. Remove via git:"
echo "  cd $REPO && git checkout HEAD -- server/main.py server/auth.py"
