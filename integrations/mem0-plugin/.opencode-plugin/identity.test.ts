import { describe, expect, test } from "bun:test";
import { resolveUserId, resolveAppId, resolveAgentId } from "./identity";

const E: Record<string, string | undefined> = {};

describe("resolveUserId (7-layer)", () => {
  test("plugin options.user_id wins over everything", () => {
    const r = resolveUserId(
      { user_id: "from-options" },
      {
        identity: {
          default: { user_id: "from-default" },
          by_editor: { opencode: "from-editor" },
          by_app: { myapp: "from-byapp" },
        },
      },
      { MEM0_USER_ID: "from-env" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-options", source: "options" });
  });

  test("by_app matches the active app_id", () => {
    const r = resolveUserId(
      undefined,
      {
        identity: {
          default: { user_id: "from-default" },
          by_editor: { opencode: "from-editor" },
          by_app: { myapp: "from-byapp", other: "wrong" },
        },
      },
      { MEM0_USER_ID: "from-env" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-byapp", source: "settings.by_app" });
  });

  test("by_editor.opencode used when no by_app match", () => {
    const r = resolveUserId(
      undefined,
      {
        identity: {
          default: { user_id: "from-default" },
          by_editor: { opencode: "from-editor", "claude-code": "wrong" },
          by_app: { other: "wrong" },
        },
      },
      { MEM0_USER_ID: "from-env" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-editor", source: "settings.by_editor" });
  });

  test("identity.default.user_id used when no by_app / by_editor", () => {
    const r = resolveUserId(
      undefined,
      { identity: { default: { user_id: "from-default" } } },
      { MEM0_USER_ID: "from-env" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-default", source: "settings.default" });
  });

  test("MEM0_USER_ID env used when settings absent", () => {
    const r = resolveUserId(
      undefined,
      null,
      { MEM0_USER_ID: "from-env" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-env", source: "env" });
  });

  test("caller fallback used when nothing else", () => {
    const r = resolveUserId(undefined, null, {}, "myapp", "from-fallback");
    expect(r).toEqual({ value: "from-fallback", source: "fallback" });
  });

  test("empty / whitespace values in higher layers are skipped", () => {
    const r = resolveUserId(
      { user_id: "" },
      { identity: { default: { user_id: "   " }, by_editor: { opencode: "" } } },
      { MEM0_USER_ID: "" },
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-fallback", source: "fallback" });
  });

  test("by_app entry can be an object with user_id", () => {
    const r = resolveUserId(
      undefined,
      { identity: { by_app: { myapp: { user_id: "obj-user" } } } },
      {},
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "obj-user", source: "settings.by_app" });
  });

  test("by_editor entry can be a plain string", () => {
    const r = resolveUserId(
      undefined,
      { identity: { by_editor: { opencode: "shortcut" } } },
      {},
      "myapp",
      "from-fallback",
    );
    expect(r).toEqual({ value: "shortcut", source: "settings.by_editor" });
  });
});

describe("resolveAppId (skips by_editor and by_app)", () => {
  test("plugin options.app_id wins", () => {
    const r = resolveAppId(
      { app_id: "from-options" },
      { identity: { default: { app_id: "from-default" } } },
      { MEM0_APP_ID: "from-env" },
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-options", source: "options" });
  });

  test("by_editor is NOT consulted for app_id", () => {
    const r = resolveAppId(
      undefined,
      {
        identity: {
          by_editor: { opencode: { app_id: "wrong-editor-app" } },
          default: { app_id: "from-default" },
        },
      },
      {},
      "from-fallback",
    );
    expect(r).toEqual({ value: "from-default", source: "settings.default" });
  });

  test("MEM0_APP_ID env used when no options/default", () => {
    const r = resolveAppId(undefined, null, { MEM0_APP_ID: "from-env" }, "fb");
    expect(r).toEqual({ value: "from-env", source: "env" });
  });

  test("fallback when nothing configured", () => {
    const r = resolveAppId(undefined, null, {}, "owner-repo");
    expect(r).toEqual({ value: "owner-repo", source: "fallback" });
  });
});

describe("resolveAgentId", () => {
  test("plugin options.agent_id wins", () => {
    const r = resolveAgentId(
      { agent_id: "from-options" },
      { identity: { default: { agent_id: "from-default" } } },
      { MEM0_AGENT_ID: "from-env" },
    );
    expect(r).toEqual({ value: "from-options", source: "options" });
  });

  test("by_editor.opencode agent_id is used when no option", () => {
    const r = resolveAgentId(
      undefined,
      {
        identity: {
          by_editor: { opencode: { agent_id: "from-editor" } },
          default: { agent_id: "from-default" },
        },
      },
      { MEM0_AGENT_ID: "from-env" },
    );
    expect(r).toEqual({ value: "from-editor", source: "settings.by_editor" });
  });

  test("identity.default.agent_id is used when no by_editor", () => {
    const r = resolveAgentId(
      undefined,
      { identity: { default: { agent_id: "from-default" } } },
      { MEM0_AGENT_ID: "from-env" },
    );
    expect(r).toEqual({ value: "from-default", source: "settings.default" });
  });

  test("MEM0_AGENT_ID env is used when settings absent", () => {
    const r = resolveAgentId(undefined, null, { MEM0_AGENT_ID: "from-env" });
    expect(r).toEqual({ value: "from-env", source: "env" });
  });

  test("undefined when no agent_id is configured", () => {
    expect(resolveAgentId(undefined, null, {})).toBeUndefined();
  });
});
