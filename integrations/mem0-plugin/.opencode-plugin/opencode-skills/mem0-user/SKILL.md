---
name: mem0-user
description: Views or changes the default user_id (and optional app_id) used by the mem0 plugin in OpenCode. Use when the user wants to set who they are for memory operations, separate from their OS username or shell env, or per-app overrides.
---

# Mem0 User Identity

View or change the default `user_id`, optional `app_id`, and optional `agent_id`
the plugin uses for memory operations. Settings persist in
`~/.mem0/settings.json` under `identity.*`. The plugin reads settings fresh on
each memory call, but resolved identity is captured ONCE at plugin startup — so
changes apply on the next OpenCode restart, not immediately.

## Resolution order (high to low)

1. Tool call arg (`user_id`)
2. Plugin options in `opencode.json` (`["@mem0/opencode-plugin", {"user_id": "..."}]`)
3. `~/.mem0/settings.json` -> `identity.by_app[<app_id>]`
4. `~/.mem0/settings.json` -> `identity.by_editor.opencode`
5. `~/.mem0/settings.json` -> `identity.default.user_id`
6. `MEM0_USER_ID` env var
7. OS username

The active sources are exported as `$MEM0_USER_ID_SOURCE`, `$MEM0_APP_ID_SOURCE`, and `$MEM0_AGENT_ID_SOURCE` to bash.

## Execution

### Step 1: Determine intent

Look at the user message:

- No `set` / `clear` / explicit id token -> **View mode** (Step 2).
- Token `set <id>` or a single bareword id (e.g. `ubuntu-opencode`) -> **Set mode** (Step 3).
- Token `clear` or `unset` -> **Clear mode** (Step 4).
- Token `by-app <appId> <id>` -> **Set per-app mode** (Step 5).
- Token `agent <agentId>` or `set-agent <agentId>` -> **Set agent mode** (Step 6).

### Step 2: View mode

Show the active identity using the env the plugin exported. Do NOT re-shell git.

```
Mem0 user identity

Active user_id:  ${MEM0_USER_ID}      (source: ${MEM0_USER_ID_SOURCE})
Active app_id:   ${MEM0_APP_ID}       (source: ${MEM0_APP_ID_SOURCE})
Active agent_id: ${MEM0_AGENT_ID:-"(unset)"} (source: ${MEM0_AGENT_ID_SOURCE:-"none"})

Configured in ~/.mem0/settings.json:
  identity.default.user_id   : <value or "(unset)">
  identity.default.agent_id  : <value or "(unset)">
  identity.by_editor.opencode: <value or "(unset)">
  identity.by_app            : <count> entries

To change: /mem0-user set <user_id>
           /mem0-user by-app <app_id> <user_id>
           /mem0-user agent <agent_id>
           /mem0-user clear
```

Read `~/.mem0/settings.json` with the Read tool. Treat missing file as `{}`.

### Step 3: Set mode (machine-wide opencode default)

1. Read `~/.mem0/settings.json` with the Read tool (missing -> `{}`).
2. Set `identity.by_editor.opencode = "<id>"`. Preserve every other key.
3. Write the file with the Write tool. 2-space indent, trailing newline.
4. Confirm:

   ```
   OpenCode default user_id set: <old or "(unset)"> -> <new>

   Saved to ~/.mem0/settings.json (identity.by_editor.opencode).
   Restart OpenCode for the change to take effect.
   ```

### Step 4: Clear mode

1. Read `~/.mem0/settings.json`. Treat missing as `{}`.
2. Remove `identity.by_editor.opencode` (and any empty parent objects). Preserve all other keys.
3. Write the file back.
4. Confirm:

   ```
   OpenCode default user_id cleared.

   On next restart the plugin will fall back to:
     identity.default.user_id -> MEM0_USER_ID env -> OS username.
   ```

### Step 5: Set per-app mode

1. Read settings. Set `identity.by_app["<app_id>"] = "<user_id>"` (string form).
2. Write the file back.
3. Confirm:

   ```
   Per-app user_id set: <app_id> -> <user_id>

   Active only when the resolved app_id matches "<app_id>" exactly.
   Restart OpenCode for the change to take effect.
   ```

### Step 6: Set agent mode

1. Read `~/.mem0/settings.json` (missing -> `{}`).
2. If the user passed a special value `clear` / `none`, remove `identity.by_editor.opencode.agent_id` and `identity.default.agent_id`. Preserve all other keys.
3. Otherwise, set `identity.default.agent_id = "<agent_id>"`. Preserve every other key.
4. Write the file back.
5. Confirm:

   ```
   Default agent_id set: <old or "(unset)"> -> <new>

   The plugin will inject this agent_id into every memory tool call that does
   not pass agent_id explicitly. Memory operations using an agent_id are
   filtered by agent_id + app_id and do NOT include user_id, so changing it
   shifts the active memory namespace.

   Restart OpenCode for the change to take effect.
   ```

## Notes

- Tool-call arg and plugin options in `opencode.json` win over this skill.
- If `$MEM0_USER_ID_SOURCE == "options"`, this skill cannot override — edit `opencode.json` instead.
- This skill never modifies `MEM0_USER_ID` or `MEM0_AGENT_ID` env (other tools may rely on them).

## Output formatting

Do NOT use markdown in output. Plain text with indentation, dashes for lists, spaces to align columns.
