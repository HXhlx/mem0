#!/usr/bin/env bash
# patch_mem0_plugin.sh — inject MEM0_HOST awareness into the user-level
# install of mem0-plugin (Claude Code variant).
#
# The plugin is installed under ~/.claude/plugins/cache/mem0-plugins/mem0/<ver>/
# and hard-codes `https://api.mem0.ai`. After running this script the same
# scripts honour the MEM0_HOST env var (falling back to https://api.mem0.ai
# when unset), so a single profile line
#
#     export MEM0_HOST="http://localhost:8888"
#
# routes every plugin REST call to the self-hosted server. Re-run after each
# plugin upgrade; the script is idempotent and creates `.self-mem0.bak`
# backups the first time it touches a file.
#
# Usage:
#   self-mem0/plugins/patch_mem0_plugin.sh            # patch latest installed version
#   self-mem0/plugins/patch_mem0_plugin.sh /custom/path  # patch a specific scripts/ dir
#   self-mem0/plugins/patch_mem0_plugin.sh --revert   # restore from .self-mem0.bak files

set -euo pipefail

REVERT=false
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --revert) REVERT=true ;;
    -h|--help)
      sed -n '1,/^set -e/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done

resolve_target() {
  if [ -n "$TARGET" ]; then
    [ -d "$TARGET" ] || { echo "not a directory: $TARGET" >&2; exit 1; }
    printf '%s' "$TARGET"
    return
  fi
  # Find the highest version directory under the Claude Code install path.
  local base="$HOME/.claude/plugins/cache/mem0-plugins/mem0"
  [ -d "$base" ] || { echo "mem0-plugin not installed under $base" >&2; exit 1; }
  local latest
  latest=$(ls -1 "$base" 2>/dev/null | sort -V | tail -1)
  [ -n "$latest" ] || { echo "no versions under $base" >&2; exit 1; }
  printf '%s/%s/scripts' "$base" "$latest"
}

SCRIPTS_DIR=$(resolve_target)
echo "→ target: $SCRIPTS_DIR"
[ -d "$SCRIPTS_DIR" ] || { echo "scripts/ not found" >&2; exit 1; }

# Files we touch — same set the in-repo plan covered.
PY_FILES=(auto_capture.py auto_import.py capture_compact_summary.py
          import_competing_tools.py on_pre_compact.py _search.py)

restore_one() {
  local f="$1"
  if [ -f "$f.self-mem0.bak" ]; then
    mv -f "$f.self-mem0.bak" "$f"
    echo "  reverted: $f"
  fi
}

if $REVERT; then
  for n in "${PY_FILES[@]}" on_session_start.sh _identity.sh; do
    restore_one "$SCRIPTS_DIR/$n"
  done
  echo "done."
  exit 0
fi

backup_once() {
  local f="$1"
  [ -f "$f.self-mem0.bak" ] || cp -p "$f" "$f.self-mem0.bak"
}

# --- Python files ------------------------------------------------------------
# Replace `API_URL = "https://api.mem0.ai"` (or SEARCH_URL = "...") with a
# version that reads MEM0_HOST. Idempotent: skip if already references
# MEM0_HOST on the same line.
patch_python_constant() {
  local f="$1" var="$2" suffix="${3:-}"
  [ -f "$f" ] || { echo "  skip (not found): $f"; return; }
  if grep -qE "^${var}\s*=.*MEM0_HOST" "$f"; then
    echo "  already patched: $f ($var)"
    return
  fi
  if ! grep -qE "^${var}\s*=\s*\"https://api.mem0.ai" "$f"; then
    echo "  no anchor in $f for $var — leaving alone"
    return
  fi
  backup_once "$f"
  if ! grep -qE "^import os(\s|$)" "$f"; then
    sed -i "0,/^import /{s|^import |import os\nimport |}" "$f"
  fi
  python3 - "$f" "$var" "$suffix" <<'PY'
import re, sys
path, var, suffix = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path).read()
pattern = re.compile(rf'^{re.escape(var)}\s*=\s*"https://api\.mem0\.ai([^"]*)"\s*$', re.M)
def repl(m):
    tail = m.group(1) or ""
    return (
        f'{var} = (os.environ.get("MEM0_HOST", "https://api.mem0.ai")'
        f'.rstrip("/")) + "{tail}"'
    )
new = pattern.sub(repl, src, count=1)
open(path, 'w').write(new)
PY
  echo "  patched: $f ($var)"
}

for n in "${PY_FILES[@]}"; do
  case "$n" in
    _search.py)
      patch_python_constant "$SCRIPTS_DIR/$n" "SEARCH_URL" "/v3/memories/search/" ;;
    *)
      patch_python_constant "$SCRIPTS_DIR/$n" "API_URL" "" ;;
  esac
done

# --- on_session_start.sh -----------------------------------------------------
# The banner-counter heredoc hard-codes api.mem0.ai in a Python literal;
# rewrite to read MEM0_HOST.
patch_session_start() {
  local f="$SCRIPTS_DIR/on_session_start.sh"
  [ -f "$f" ] || { echo "  skip (not found): on_session_start.sh"; return; }
  if grep -q "os.environ.get('MEM0_HOST'" "$f"; then
    echo "  already patched: on_session_start.sh"
    return
  fi
  if ! grep -q "'https://api.mem0.ai/v3/memories/" "$f"; then
    echo "  no anchor in on_session_start.sh — leaving alone"
    return
  fi
  backup_once "$f"
  python3 - "$f" <<'PY'
import sys
path = sys.argv[1]
src = open(path).read()
old = "global_search = os.environ.get('MEM0_GLOBAL_SEARCH', 'false') == 'true'\n"
new = old + "api_base = os.environ.get('MEM0_HOST', 'https://api.mem0.ai').rstrip('/')\n"
if old not in src:
    sys.exit(0)
src = src.replace(old, new, 1)
src = src.replace(
    "'https://api.mem0.ai/v3/memories/?page=1&page_size=1'",
    "f'{api_base}/v3/memories/?page=1&page_size=1'",
)
open(path, 'w').write(src)
PY
  echo "  patched: on_session_start.sh"
}
patch_session_start

# --- _identity.sh ------------------------------------------------------------
patch_identity() {
  local f="$SCRIPTS_DIR/_identity.sh"
  [ -f "$f" ] || { echo "  skip (not found): _identity.sh"; return; }
  if grep -q "self-mem0: MEM0_HOST passthrough" "$f"; then
    echo "  already patched: _identity.sh"
    return
  fi
  backup_once "$f"
  cat >> "$f" <<'SH'

# self-mem0: MEM0_HOST passthrough (added by patch_mem0_plugin.sh).
# Honours either explicit env or Claude Code userConfig injection so the
# plugin's REST calls land on the self-hosted server without touching code.
if [ -z "${MEM0_HOST:-}" ] && [ -n "${CLAUDE_PLUGIN_OPTION_HOST:-}" ]; then
  MEM0_HOST="$CLAUDE_PLUGIN_OPTION_HOST"
fi
if [ -z "${MEM0_HOST:-}" ] && [ -n "${CLAUDE_PLUGIN_OPTION_MEM0_HOST:-}" ]; then
  MEM0_HOST="$CLAUDE_PLUGIN_OPTION_MEM0_HOST"
fi
if [ -n "${MEM0_HOST:-}" ]; then
  export MEM0_HOST
fi
SH
  echo "  patched: _identity.sh"
}
patch_identity

echo "done. To revert: $0 --revert"
