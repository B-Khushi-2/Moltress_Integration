// @vitest-environment node
import { describe, it, expect, afterEach, beforeEach } from "vitest";
import http from "http";
import type { AddressInfo } from "net";
import { mkdtempSync, writeFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import {
  buildChatRequest,
  describeBackendError,
  getMoltressConfig,
  getMoltressStatus,
  isMoltressEnabled,
  loadMoltressEnvFile,
  parseDotEnv,
  sendMessageViaMoltress,
  type MoltressConfig,
} from "../src/main/moltress";

// ── helpers ─────────────────────────────────────────────────────────

type Handler = (
  req: http.IncomingMessage,
  body: string,
  res: http.ServerResponse,
) => void;

const servers: http.Server[] = [];

async function startServer(handler: Handler): Promise<string> {
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => handler(req, body, res));
  });
  servers.push(server);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

function json(
  res: http.ServerResponse,
  status: number,
  payload: unknown,
): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (s) =>
        new Promise<void>((r) => {
          s.closeAllConnections?.();
          s.close(() => r());
        }),
    ),
  );
});

function cfg(url: string, over: Partial<MoltressConfig> = {}): MoltressConfig {
  return {
    enabled: true,
    backendUrl: url,
    apiToken: "",
    timeoutMs: 5000,
    ...over,
  };
}

interface Outcome {
  chunks: string[];
  done: Array<string | undefined>;
  errors: string[];
  tools: Array<{ name: string; status: string }>;
}

function run(
  message: string,
  config: MoltressConfig,
  extra: Parameters<typeof sendMessageViaMoltress>[2] = {},
): Promise<Outcome & { abort: () => void }> {
  const out: Outcome = { chunks: [], done: [], errors: [], tools: [] };
  return new Promise((resolve) => {
    const finish = (): void => resolve({ ...out, abort: handle.abort });
    const handle = sendMessageViaMoltress(
      message,
      {
        onChunk: (c) => out.chunks.push(c),
        onDone: (id) => {
          out.done.push(id);
          finish();
        },
        onError: (e) => {
          out.errors.push(e);
          finish();
        },
        onToolEvent: (t) => out.tools.push({ name: t.name, status: t.status }),
      },
      { config, ...extra },
    );
  });
}

// ── config ──────────────────────────────────────────────────────────

describe("getMoltressConfig", () => {
  it("defaults to enabled, localhost backend, 10 minute timeout", () => {
    const c = getMoltressConfig({});
    expect(c).toEqual({
      enabled: true,
      backendUrl: "http://127.0.0.1:8765",
      apiToken: "",
      timeoutMs: 600000,
    });
  });

  it("reads overrides and trims trailing slashes", () => {
    const c = getMoltressConfig({
      MOLTRESS_BACKEND_URL: "http://example.test:9000//",
      MOLTRESS_API_TOKEN: " tok ",
      MOLTRESS_REQUEST_TIMEOUT_MS: "1234",
    });
    expect(c.backendUrl).toBe("http://example.test:9000");
    expect(c.apiToken).toBe("tok");
    expect(c.timeoutMs).toBe(1234);
  });

  it("falls back to the default timeout for invalid values", () => {
    expect(
      getMoltressConfig({ MOLTRESS_REQUEST_TIMEOUT_MS: "abc" }).timeoutMs,
    ).toBe(600000);
    expect(
      getMoltressConfig({ MOLTRESS_REQUEST_TIMEOUT_MS: "-5" }).timeoutMs,
    ).toBe(600000);
  });

  it.each(["false", "0", "no", "OFF"])(
    "MOLTRESS_ENABLED=%s disables it",
    (v) => {
      expect(isMoltressEnabled({ MOLTRESS_ENABLED: v })).toBe(false);
    },
  );

  it.each([undefined, "", "true", "1"])(
    "MOLTRESS_ENABLED=%s keeps it enabled",
    (v) => {
      expect(
        isMoltressEnabled(v === undefined ? {} : { MOLTRESS_ENABLED: v }),
      ).toBe(true);
    },
  );
});

describe(".env loading", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "moltress-env-"));
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it("parses comments, quotes, export and inline comments", () => {
    const parsed = parseDotEnv(
      [
        "# c",
        "A=1",
        'export B="two words"',
        "C='x'",
        "D=val # trailing",
        "",
        "bad line",
      ].join("\n"),
    );
    expect(parsed).toEqual({ A: "1", B: "two words", C: "x", D: "val" });
  });

  it("imports only MOLTRESS_* keys and never overrides existing env", () => {
    writeFileSync(
      join(dir, ".env"),
      "MOLTRESS_BACKEND_URL=http://from-file:1\nMOLTRESS_API_TOKEN=file-token\nOLLAMA_MODEL=x\nSECRET=y\n",
    );
    const env: NodeJS.ProcessEnv = { MOLTRESS_API_TOKEN: "already-set" };
    const used = loadMoltressEnvFile([dir], env);
    expect(used).toBe(join(dir, ".env"));
    expect(env.MOLTRESS_BACKEND_URL).toBe("http://from-file:1");
    expect(env.MOLTRESS_API_TOKEN).toBe("already-set");
    expect(env.OLLAMA_MODEL).toBeUndefined();
    expect(env.SECRET).toBeUndefined();
  });

  it("returns null when there is no .env", () => {
    expect(loadMoltressEnvFile([dir], {})).toBeNull();
  });
});

// ── request mapping ─────────────────────────────────────────────────

describe("buildChatRequest", () => {
  it("passes history, context folder and trims the query", () => {
    const r = buildChatRequest("  hello  ", {
      history: [{ role: "agent", content: "hi" }],
      contextFolder: "/work/app",
    });
    expect(r).toMatchObject({
      query: "hello",
      mode: "auto",
      history: [{ role: "agent", content: "hi" }],
      context_folder: "/work/app",
    });
  });

  it("maps /pipeline to pipeline mode", () => {
    const r = buildChatRequest("/pipeline KeyError in login.py", {});
    expect(r.mode).toBe("pipeline");
    expect(r.query).toBe("KeyError in login.py");
    expect(buildChatRequest("/pipeline", {}).query).toBe("");
  });

  it("forwards text attachments and reports the unsupported ones", () => {
    const r = buildChatRequest("look", {
      attachments: [
        {
          id: "1",
          kind: "text-file",
          name: "a.py",
          mime: "text/x-python",
          size: 3,
          text: "x=1",
        },
        {
          id: "2",
          kind: "image",
          name: "p.png",
          mime: "image/png",
          size: 9,
          dataUrl: "data:...",
        },
        {
          id: "3",
          kind: "path-ref",
          name: "d.pdf",
          mime: "application/pdf",
          size: 9,
          path: "/d.pdf",
        },
      ],
    });
    expect(r.files).toEqual([{ path: "a.py", content: "x=1" }]);
    expect(r.ignored_attachments).toEqual(["p.png", "d.pdf"]);
    expect(JSON.stringify(r)).not.toContain("data:...");
  });
});

// ── transport against a real HTTP server ─────────────────────────────

describe("sendMessageViaMoltress", () => {
  it("delivers the real answer as one chunk, then done with no session id", async () => {
    let seen: { url?: string; body?: Record<string, unknown> } = {};
    const url = await startServer((req, body, res) => {
      seen = { url: req.url, body: JSON.parse(body) };
      json(res, 200, {
        ok: true,
        request_id: "r1",
        agent: "developer_agent",
        status: "success",
        answer: "It is a desktop chat app.",
        tools_used: [{ tool_name: "read_file", success: true }],
      });
    });
    const out = await run(
      "Explain the purpose of this application.",
      cfg(url),
      {
        history: [{ role: "user", content: "earlier" }],
        contextFolder: "/proj",
      },
    );
    expect(out.errors).toEqual([]);
    expect(out.chunks).toEqual(["It is a desktop chat app."]);
    expect(out.done).toEqual([undefined]);
    expect(out.tools).toEqual([{ name: "read_file", status: "completed" }]);
    expect(seen.url).toBe("/api/agent/chat");
    expect(seen.body).toMatchObject({
      query: "Explain the purpose of this application.",
      context_folder: "/proj",
      history: [{ role: "user", content: "earlier" }],
    });
  });

  it("sends the bearer token when configured", async () => {
    let auth: string | undefined;
    const url = await startServer((req, _b, res) => {
      auth = req.headers.authorization;
      json(res, 200, {
        ok: true,
        request_id: "r",
        status: "success",
        answer: "ok",
      });
    });
    await run("hi", cfg(url, { apiToken: "s3cret" }));
    expect(auth).toBe("Bearer s3cret");
  });

  it("rejects an empty query client-side without calling the backend", async () => {
    let called = false;
    const url = await startServer((_r, _b, res) => {
      called = true;
      json(res, 200, {});
    });
    const out = await run("   ", cfg(url));
    expect(out.errors[0]).toMatch(/enter a question/i);
    expect(called).toBe(false);
    const p = await run("/pipeline", cfg(url));
    expect(p.errors[0]).toMatch(/\/pipeline/);
  });

  it("explains how to start the backend when it is unreachable", async () => {
    const url = await startServer((_r, _b, res) => json(res, 200, {}));
    await afterEachClose();
    const out = await run("hi", cfg(url));
    expect(out.chunks).toEqual([]);
    expect(out.errors).toHaveLength(1);
    expect(out.errors[0]).toContain("Cannot reach the Moltress backend");
    expect(out.errors[0]).toContain("npm run backend");
  });

  it("surfaces the backend's error message for Ollama-unavailable (503)", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 503, {
        ok: false,
        request_id: "r",
        status: "error",
        error: {
          type: "LLMUnavailable",
          message:
            "Local LLM (Ollama) is not reachable at http://localhost:11434.",
        },
      }),
    );
    const out = await run("hi", cfg(url));
    expect(out.errors).toEqual([
      "Local LLM (Ollama) is not reachable at http://localhost:11434.",
    ]);
    expect(out.chunks).toEqual([]);
  });

  it("surfaces agent validation failures (502 MalformedOutput)", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 502, {
        ok: false,
        request_id: "r",
        status: "error",
        error: {
          type: "MalformedOutput",
          message: "Model output did not match the expected schema",
        },
      }),
    );
    const out = await run("hi", cfg(url));
    expect(out.errors[0]).toMatch(/did not match the expected schema/);
  });

  it("reports an invalid token (401) clearly", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 401, {
        ok: false,
        error: { type: "Unauthorized", message: "x" },
      }),
    );
    const out = await run("hi", cfg(url));
    expect(out.errors[0]).toMatch(/MOLTRESS_API_TOKEN/);
  });

  it("handles a non-JSON reply (e.g. a proxy error page)", async () => {
    const url = await startServer((_r, _b, res) => {
      res.writeHead(502, { "Content-Type": "text/html" });
      res.end("<html>Bad gateway</html>");
    });
    const out = await run("hi", cfg(url));
    expect(out.errors[0]).toBe("The Moltress backend returned HTTP 502.");
  });

  it("treats an empty answer as an error instead of a blank bubble", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 200, {
        ok: true,
        request_id: "r",
        status: "success",
        answer: "  ",
      }),
    );
    const out = await run("hi", cfg(url));
    expect(out.errors).toEqual(["The agent returned an empty response."]);
  });

  it("times out with an actionable message", async () => {
    const url = await startServer(() => {
      /* never respond */
    });
    const out = await run("hi", cfg(url, { timeoutMs: 150 }));
    expect(out.errors[0]).toMatch(/did not answer within/);
  });

  it("abort() cancels the request quietly (no error)", async () => {
    let received = false;
    const url = await startServer(() => {
      received = true; // hold the connection open
    });
    const out = new Promise<Outcome>((resolve) => {
      const o: Outcome = { chunks: [], done: [], errors: [], tools: [] };
      const h = sendMessageViaMoltress(
        "hi",
        {
          onChunk: (c) => o.chunks.push(c),
          onDone: () => (o.done.push(undefined), resolve(o)),
          onError: (e) => (o.errors.push(e), resolve(o)),
        },
        { config: cfg(url) },
      );
      const wait = setInterval(() => {
        if (received) {
          clearInterval(wait);
          h.abort();
        }
      }, 10);
    });
    const o = await out;
    expect(o.errors).toEqual([]);
    expect(o.chunks).toEqual([]);
  });
});

async function afterEachClose(): Promise<void> {
  await Promise.all(
    servers.splice(0).map(
      (s) =>
        new Promise<void>((r) => {
          s.closeAllConnections?.();
          s.close(() => r());
        }),
    ),
  );
}

// ── status ──────────────────────────────────────────────────────────

describe("getMoltressStatus", () => {
  it("is ready when the backend reports ok", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 200, {
        status: "ok",
        problems: [],
        agents: ["developer_agent"],
        ollama: {
          reachable: true,
          base_url: "http://localhost:11434",
          model: "qwen2.5-coder:7b",
          model_available: true,
        },
      }),
    );
    const s = await getMoltressStatus({ config: cfg(url) });
    expect(s).toMatchObject({
      enabled: true,
      backendReachable: true,
      ready: true,
      problems: [],
    });
    expect(s.ollama?.model).toBe("qwen2.5-coder:7b");
  });

  it("is reachable-but-degraded when Ollama is down", async () => {
    const url = await startServer((_r, _b, res) =>
      json(res, 200, {
        status: "degraded",
        problems: ["Ollama is not reachable"],
        agents: [],
      }),
    );
    const s = await getMoltressStatus({ config: cfg(url) });
    expect(s).toMatchObject({ backendReachable: true, ready: false });
    expect(s.problems).toEqual(["Ollama is not reachable"]);
  });

  it("reports an unreachable backend", async () => {
    const url = await startServer((_r, _b, res) => json(res, 200, {}));
    await afterEachClose();
    const s = await getMoltressStatus({ config: cfg(url) });
    expect(s.backendReachable).toBe(false);
    expect(s.ready).toBe(false);
    expect(s.problems[0]).toContain("Cannot reach the Moltress backend");
  });

  it("does not probe anything when disabled", async () => {
    const s = await getMoltressStatus({
      config: cfg("http://127.0.0.1:1", { enabled: false }),
    });
    expect(s).toMatchObject({
      enabled: false,
      backendReachable: false,
      problems: [],
    });
  });
});

describe("describeBackendError", () => {
  it("falls back to the HTTP status when there is no envelope", () => {
    expect(describeBackendError(500, null)).toBe(
      "The Moltress backend returned HTTP 500.",
    );
  });
});
