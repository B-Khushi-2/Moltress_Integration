/**
 * Moltress Agent Layer transport.
 *
 * Sends a chat turn from the desktop UI to the Moltress backend
 * (`backend/`, FastAPI) over HTTP and feeds the real agent answer back
 * through the same `ChatCallbacks` the renderer already understands:
 *
 *   renderer --IPC send-message--> main --HTTP--> backend --> Agent Layer --> Ollama
 *
 * The backend runs the request through the AgentRouter / AgentOrchestrator
 * and the local model. The Agent Layer produces one validated, structured
 * answer per request (it is not token-streamed), so this transport uses a
 * reliable request/response flow and delivers the answer as a single chunk.
 *
 * Configuration (environment, optionally from `<app>/.env`; see .env.example):
 *   MOLTRESS_ENABLED             default "true"; "false" restores stock Hermes behaviour
 *   MOLTRESS_BACKEND_URL         default http://127.0.0.1:8765
 *   MOLTRESS_API_TOKEN           optional bearer token (must match the backend)
 *   MOLTRESS_REQUEST_TIMEOUT_MS  default 600000 (local 7B models can be slow)
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";
import type { Attachment } from "../shared/attachments";

// ── Types (mirror backend/models.py) ────────────────────────────────

export interface MoltressConfig {
  enabled: boolean;
  backendUrl: string;
  apiToken: string;
  timeoutMs: number;
}

export interface MoltressChatError {
  type: string;
  message: string;
  recoverable?: boolean;
}

export interface MoltressChatResponse {
  ok: boolean;
  request_id: string;
  agent?: string | null;
  status: "success" | "partial" | "needs_input" | "error";
  answer?: string;
  error?: MoltressChatError | null;
  tools_used?: Array<{ tool_name: string; success: boolean }>;
}

export interface MoltressStatus {
  enabled: boolean;
  backendUrl: string;
  /** Backend process reachable and speaking the Moltress API. */
  backendReachable: boolean;
  /** Backend says Ollama is up and the configured model is pulled. */
  ready: boolean;
  problems: string[];
  ollama?: {
    reachable: boolean;
    base_url: string;
    model: string;
    model_available: boolean | null;
  };
  agents?: string[];
}

/** Subset of ChatCallbacks / ChatHandle this transport needs (avoids a
 *  circular import with hermes.ts, which imports this module). */
export interface MoltressCallbacks {
  onChunk: (text: string) => void;
  onDone: (sessionId?: string) => void;
  onError: (error: string) => void;
  onToolEvent?: (event: {
    callId: string;
    name: string;
    status: "running" | "completed" | "failed";
    label?: string;
  }) => void;
}

export interface MoltressHandle {
  abort: () => void;
}

export interface MoltressSendOptions {
  history?: Array<{ role: string; content: string }>;
  attachments?: Attachment[];
  contextFolder?: string;
  sessionId?: string;
  /** Test seam. */
  fetchImpl?: typeof fetch;
  config?: MoltressConfig;
}

// ── Configuration ───────────────────────────────────────────────────

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765";
const DEFAULT_TIMEOUT_MS = 600_000;
const ENV_FILE_KEY_PREFIX = "MOLTRESS_";

function truthy(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === "") return fallback;
  return ["0", "false", "no", "off"].indexOf(value.trim().toLowerCase()) === -1;
}

export function getMoltressConfig(
  env: NodeJS.ProcessEnv = process.env,
): MoltressConfig {
  const timeout = Number.parseInt(env.MOLTRESS_REQUEST_TIMEOUT_MS ?? "", 10);
  return {
    enabled: truthy(env.MOLTRESS_ENABLED, true),
    backendUrl: (
      env.MOLTRESS_BACKEND_URL?.trim() || DEFAULT_BACKEND_URL
    ).replace(/\/+$/, ""),
    apiToken: env.MOLTRESS_API_TOKEN?.trim() ?? "",
    timeoutMs:
      Number.isFinite(timeout) && timeout > 0 ? timeout : DEFAULT_TIMEOUT_MS,
  };
}

export function isMoltressEnabled(
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  return getMoltressConfig(env).enabled;
}

/** Parse a dotenv-style file into key/value pairs (no interpolation). */
export function parseDotEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line
      .slice(0, eq)
      .trim()
      .replace(/^export\s+/, "");
    let value = line.slice(eq + 1).trim();
    const quoted = /^(['"])(.*)\1$/.exec(value);
    if (quoted) value = quoted[2];
    else value = value.replace(/\s+#.*$/, "");
    out[key] = value;
  }
  return out;
}

/**
 * Load `MOLTRESS_*` settings from the first `.env` found in `dirs` into
 * `env`, never overriding variables that are already set. Only MOLTRESS_
 * keys are imported: the rest of the file (OLLAMA_*, ...) belongs to the
 * Python side, and importing everything would leak unrelated settings into
 * the Electron process.
 */
export function loadMoltressEnvFile(
  dirs: string[],
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const explicit = env.MOLTRESS_ENV_FILE?.trim();
  const candidates = explicit ? [explicit] : dirs.map((d) => join(d, ".env"));
  for (const file of candidates) {
    try {
      if (!existsSync(file)) continue;
      const parsed = parseDotEnv(readFileSync(file, "utf-8"));
      for (const [key, value] of Object.entries(parsed)) {
        if (key.startsWith(ENV_FILE_KEY_PREFIX) && env[key] === undefined) {
          env[key] = value;
        }
      }
      return file;
    } catch {
      // unreadable .env: fall through to the next candidate
    }
  }
  return null;
}

// ── Request mapping ─────────────────────────────────────────────────

const PIPELINE_PREFIX = /^\/pipeline(?:\s+|$)/i;

export interface BuiltRequest {
  query: string;
  mode: "auto" | "pipeline";
  history: Array<{ role: string; content: string }>;
  files: Array<{ path: string; content: string }>;
  ignored_attachments: string[];
  context_folder?: string;
  session_id?: string;
}

export function buildChatRequest(
  message: string,
  opts: Pick<MoltressSendOptions, "history" | "attachments" | "contextFolder" | "sessionId">,
): BuiltRequest {
  let query = message.trim();
  let mode: "auto" | "pipeline" = "auto";
  // `/pipeline <problem>` runs Debugging -> Developer -> Testing.
  if (PIPELINE_PREFIX.test(query)) {
    mode = "pipeline";
    query = query.replace(PIPELINE_PREFIX, "").trim();
  }

  const files: BuiltRequest["files"] = [];
  const ignored: string[] = [];
  for (const a of opts.attachments ?? []) {
    if (a.kind === "text-file" && typeof a.text === "string") {
      files.push({ path: a.name, content: a.text });
    } else {
      ignored.push(a.name);
    }
  }

  return {
    query,
    mode,
    history: (opts.history ?? []).map((m) => ({
      role: m.role,
      content: m.content,
    })),
    files,
    ignored_attachments: ignored,
    ...(opts.contextFolder ? { context_folder: opts.contextFolder } : {}),
    ...(opts.sessionId ? { session_id: opts.sessionId } : {}),
  };
}

// ── HTTP ────────────────────────────────────────────────────────────

function headers(cfg: MoltressConfig): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...(cfg.apiToken ? { Authorization: `Bearer ${cfg.apiToken}` } : {}),
  };
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

function describeConnectionFailure(cfg: MoltressConfig, err: unknown): string {
  const cause = (err as { cause?: { code?: string; message?: string } })?.cause;
  const detail = cause?.code || cause?.message || (err as Error)?.message || "";
  return (
    `Cannot reach the Moltress backend at ${cfg.backendUrl}` +
    (detail ? ` (${detail})` : "") +
    `. Start it with "npm run backend" (or "python -m backend") and check MOLTRESS_BACKEND_URL.`
  );
}

/** Turn a non-2xx / error-envelope reply into one readable message. */
export function describeBackendError(
  status: number,
  body: Partial<MoltressChatResponse> | null,
): string {
  const err = body?.error;
  if (status === 401) {
    return "The Moltress backend rejected the request: missing or invalid API token. Set the same MOLTRESS_API_TOKEN for the app and the backend.";
  }
  if (err?.message) {
    return err.message;
  }
  return `The Moltress backend returned HTTP ${status}.`;
}

export async function getMoltressStatus(
  opts: { fetchImpl?: typeof fetch; config?: MoltressConfig } = {},
): Promise<MoltressStatus> {
  const cfg = opts.config ?? getMoltressConfig();
  const doFetch = opts.fetchImpl ?? fetch;
  const base: MoltressStatus = {
    enabled: cfg.enabled,
    backendUrl: cfg.backendUrl,
    backendReachable: false,
    ready: false,
    problems: [],
  };
  if (!cfg.enabled) return base;

  try {
    const res = await doFetch(`${cfg.backendUrl}/api/health`, {
      headers: headers(cfg),
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 401) {
      return {
        ...base,
        backendReachable: true,
        problems: [describeBackendError(401, null)],
      };
    }
    const h = (await res.json()) as {
      status: string;
      problems?: string[];
      agents?: string[];
      ollama?: MoltressStatus["ollama"];
    };
    return {
      ...base,
      backendReachable: true,
      ready: h.status === "ok",
      problems: h.problems ?? [],
      ollama: h.ollama,
      agents: h.agents,
    };
  } catch (err) {
    return { ...base, problems: [describeConnectionFailure(cfg, err)] };
  }
}

/**
 * Send one chat turn to the Agent Layer via the backend.
 * Returns synchronously with an abort handle; results arrive via callbacks.
 */
export function sendMessageViaMoltress(
  message: string,
  cb: MoltressCallbacks,
  opts: MoltressSendOptions = {},
): MoltressHandle {
  const cfg = opts.config ?? getMoltressConfig();
  const doFetch = opts.fetchImpl ?? fetch;
  const controller = new AbortController();
  let settled = false;
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, cfg.timeoutMs);

  const finish = (fn: () => void): void => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    fn();
  };

  const request = buildChatRequest(message, opts);

  void (async () => {
    // Always deliver callbacks asynchronously, after the caller has received
    // the handle (the IPC layer registers it only once we return).
    await Promise.resolve();

    // Client-side guard: never send an empty prompt to the model.
    if (!request.query) {
      finish(() =>
        cb.onError(
          request.mode === "pipeline"
            ? "Please describe the problem after /pipeline, e.g. /pipeline KeyError in login.py"
            : "Please enter a question or request for the agent.",
        ),
      );
      return;
    }

    let res: Response;
    try {
      res = await doFetch(`${cfg.backendUrl}/api/agent/chat`, {
        method: "POST",
        headers: headers(cfg),
        body: JSON.stringify(request),
        signal: controller.signal,
      });
    } catch (err) {
      finish(() => {
        if (isAbortError(err)) {
          // User abort is silent; a timeout is an error worth showing.
          if (timedOut) {
            cb.onError(
              `The agent did not answer within ${Math.round(cfg.timeoutMs / 1000)}s. The local model may be overloaded; try again or raise MOLTRESS_REQUEST_TIMEOUT_MS.`,
            );
          } else {
            cb.onDone();
          }
          return;
        }
        cb.onError(describeConnectionFailure(cfg, err));
      });
      return;
    }

    let body: MoltressChatResponse | null = null;
    try {
      body = (await res.json()) as MoltressChatResponse;
    } catch (err) {
      if (isAbortError(err)) {
        finish(() =>
          timedOut
            ? cb.onError(
                `The agent did not answer within ${Math.round(cfg.timeoutMs / 1000)}s.`,
              )
            : cb.onDone(),
        );
        return;
      }
      // Non-JSON reply: not a Moltress backend (or a proxy error page).
    }

    finish(() => {
      if (!res.ok || !body || body.ok === false) {
        cb.onError(describeBackendError(res.status, body));
        return;
      }
      const answer = (body.answer ?? "").trim();
      if (!answer) {
        cb.onError("The agent returned an empty response.");
        return;
      }
      // Surface which tools the agent really ran (read-only evidence).
      (body.tools_used ?? []).forEach((t, i) => {
        cb.onToolEvent?.({
          callId: `${body!.request_id}:${i}`,
          name: t.tool_name,
          status: t.success ? "completed" : "failed",
          label: t.tool_name,
        });
      });
      cb.onChunk(answer);
      // Pass the session ID back so the renderer reconciles with DB.
      cb.onDone(opts.sessionId || body.request_id);
    });
  })();

  return {
    abort: () => {
      if (settled) return;
      controller.abort();
    },
  };
}
