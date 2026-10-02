/**
 * Default models seeded on first install.
 *
 * Contributors: add new models here! They'll be available to all users
 * on fresh install. Format:
 *   { name: "Display Name", provider: "provider-key", model: "model-id", baseUrl: "" }
 *
 * Provider keys: openrouter, anthropic, openai, custom
 * For openrouter models, use the full path (e.g. "anthropic/claude-sonnet-4-20250514")
 * For direct provider models, use the provider's model ID (e.g. "claude-sonnet-4-20250514")
 */

export interface DefaultModel {
  name: string;
  provider: string;
  model: string;
  baseUrl: string;
}

const DEFAULT_MODELS: DefaultModel[] = [
  // ── DeepSeek (direct) ────────────────────────────────────────────────
  {
    name: "DeepSeek V3",
    provider: "deepseek",
    model: "deepseek-chat",
    baseUrl: "https://api.deepseek.com/v1",
  },
  {
    name: "DeepSeek R1",
    provider: "deepseek",
    model: "deepseek-reasoner",
    baseUrl: "https://api.deepseek.com/v1",
  },

  // ── Ollama (Local) ───────────────────────────────────────────────────
  {
    name: "Ollama Llama 3 (Local)",
    provider: "ollama",
    model: "llama3",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "Ollama DeepSeek-R1 (Local)",
    provider: "ollama",
    model: "deepseek-r1",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "Ollama Qwen 2.5 (Local)",
    provider: "ollama",
    model: "qwen2.5",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "Ollama Mistral (Local)",
    provider: "ollama",
    model: "mistral",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "Ollama CodeLlama (Local)",
    provider: "ollama",
    model: "codellama",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "DeepSeek V4 Pro (Ollama)",
    provider: "ollama",
    model: "deepseek-ai/deepseek-v4-pro",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "DeepSeek V4 Flash (Ollama)",
    provider: "ollama",
    model: "deepseek-ai/deepseek-v4-flash",
    baseUrl: "http://localhost:11434/v1",
  },
  {
    name: "Qwen3-235B Instruct (Ollama)",
    provider: "ollama",
    model: "qwen3-235b-instruct",
    baseUrl: "http://localhost:11434/v1",
  },
];

export default DEFAULT_MODELS;
