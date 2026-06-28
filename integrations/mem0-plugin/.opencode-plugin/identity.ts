export interface PluginOptions {
  user_id?: string;
  app_id?: string;
  agent_id?: string;
}

export type ResolvedSource =
  | "options"
  | "settings.by_app"
  | "settings.by_editor"
  | "settings.default"
  | "env"
  | "fallback";

export interface ResolvedField {
  value: string;
  source: ResolvedSource;
}

function pick(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function identity(settings: Record<string, unknown> | null | undefined): Record<string, any> {
  const value = settings?.identity;
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

function entry(value: unknown): { user_id?: string; app_id?: string; agent_id?: string } {
  if (typeof value === "string") return { user_id: value };
  if (value && typeof value === "object") return value as { user_id?: string; app_id?: string; agent_id?: string };
  return {};
}

export function resolveUserId(
  options: PluginOptions | undefined,
  settings: Record<string, unknown> | null | undefined,
  env: Record<string, string | undefined>,
  appId: string,
  fallback: string,
): ResolvedField {
  const fromOptions = pick(options?.user_id);
  if (fromOptions) return { value: fromOptions, source: "options" };

  const id = identity(settings);
  const fromApp = pick(entry(id.by_app?.[appId]).user_id);
  if (fromApp) return { value: fromApp, source: "settings.by_app" };

  const fromEditor = pick(entry(id.by_editor?.opencode).user_id);
  if (fromEditor) return { value: fromEditor, source: "settings.by_editor" };

  const fromDefault = pick(id.default?.user_id);
  if (fromDefault) return { value: fromDefault, source: "settings.default" };

  const fromEnv = pick(env.MEM0_USER_ID);
  if (fromEnv) return { value: fromEnv, source: "env" };

  return { value: fallback, source: "fallback" };
}

export function resolveAppId(
  options: PluginOptions | undefined,
  settings: Record<string, unknown> | null | undefined,
  env: Record<string, string | undefined>,
  fallback: string,
): ResolvedField {
  const fromOptions = pick(options?.app_id);
  if (fromOptions) return { value: fromOptions, source: "options" };

  const fromDefault = pick(identity(settings).default?.app_id);
  if (fromDefault) return { value: fromDefault, source: "settings.default" };

  const fromEnv = pick(env.MEM0_APP_ID);
  if (fromEnv) return { value: fromEnv, source: "env" };

  return { value: fallback, source: "fallback" };
}

export function resolveAgentId(
  options: PluginOptions | undefined,
  settings: Record<string, unknown> | null | undefined,
  env: Record<string, string | undefined>,
): ResolvedField | undefined {
  const fromOptions = pick(options?.agent_id);
  if (fromOptions) return { value: fromOptions, source: "options" };

  const id = identity(settings);
  const fromEditor = pick(entry(id.by_editor?.opencode).agent_id);
  if (fromEditor) return { value: fromEditor, source: "settings.by_editor" };

  const fromDefault = pick(id.default?.agent_id);
  if (fromDefault) return { value: fromDefault, source: "settings.default" };

  const fromEnv = pick(env.MEM0_AGENT_ID);
  if (fromEnv) return { value: fromEnv, source: "env" };

  return undefined;
}
