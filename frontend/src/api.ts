// Thin typed client for the Python API.

export type DatasetStatus = "pending" | "running" | "done" | "error" | "cancelled";

export interface Dataset {
  id: number;
  source_url: string;
  title: string;
  status: DatasetStatus;
  error: string | null;
  range_days: number;
  created_at: number;
  finished_at: number | null;
  post_count: number;
  comment_count: number;
  page_count: number;
  word_count: number;
  source_type: "facebook" | "website";
  index_state: "" | "building" | "ready" | "keyword-only";
  job?: Job | null;
}

export interface Job {
  dataset_id: number;
  status: DatasetStatus;
  stage: string;
  message: string;
  posts_found: number;
  posts_done: number;
  comments: number;
  pages_found?: number;
  pages_done?: number;
  words?: number;
  started_at: number;
  error: string | null;
  title?: string;
}

export interface Comment {
  id: number;
  text: string;
  created_at: number | null;
  reactions: number | null;
  is_reply: number;
}

export interface Post {
  id: number;
  text: string;
  created_at: number | null;
  reactions: number | null;
  shares: number | null;
  comment_total: number | null;
  comments: Comment[];
}

export interface BriefPost {
  id: number;
  text: string;
  created_at: number | null;
  comments: number;
  reactions: number | null;
  shares: number | null;
  comment_total: number | null;
}

export interface PageRow {
  id: number;
  url: string;
  status: number | null;
  title: string;
  description: string;
  lang: string | null;
  published: string | null;
  text: string;
  word_count: number;
  headings: [number, string][];
  meta: {
    canonical?: string;
    h1_count?: number;
    links_internal?: number;
    links_external?: number;
    images?: number;
    images_no_alt?: number;
    elapsed_ms?: number | null;
    size_kb?: number | null;
  };
  rendered: number;
}

export interface PageRef { id: number; no: number; url: string; title: string }

export interface SiteOverview {
  type: "website";
  totals: { pages: number; ok_pages: number; words: number; avg_words: number; issues: number; rendered: number; avg_ms: number };
  languages: { lang: string; pages: number }[];
  keywords: { word: string; count: number }[];
  pages: (PageRef & { words: number; status: number | null; ms: number | null })[];
  issues: { severity: "error" | "warning" | "info"; title: string; detail: string; count: number; pages: PageRef[] }[];
}

export interface Tier {
  id: string;
  label: string;
  model: string;
  name: string;
  download_gb: number;
  num_ctx: number;
  why: string;
  min_vram_gb: number;
  min_unified_gb: number;
  min_ram_gb: number;
}

export interface LocalStatus {
  supported: boolean;
  reasons: string[];
  tier: Tier | null;
  hardware: { ram_gb: number; vram_gb: number; apple_silicon: boolean; gpus: { vendor: string; name: string; vram_gb: number }[]; free_disk_gb: number };
  catalog_version: string;
  running: boolean;
  installed: Tier[];
  allowed: Tier[];
  active: Tier | null;
  recommended: Tier | null;
  update_available: boolean;
  pull: { model: string | null; status: "idle" | "downloading" | "done" | "error"; completed: number; total: number; error: string | null };
  updated?: boolean;
}

export interface Overview {
  totals: {
    posts: number;
    comments: number;
    replies: number;
    reactions: number;
    avg_comments_per_post: number;
    avg_comment_length: number;
  };
  range: { first: number | null; last: number | null };
  timeline: { date: string; posts: number; comments: number }[];
  hours: number[];
  post_keywords: { word: string; count: number }[];
  comment_keywords: { word: string; count: number }[];
  most_discussed: BriefPost[];
  most_reacted: BriefPost[];
}

export interface FacebookState {
  logged_in: boolean | null;
  checking: boolean;
  login_running: boolean;
  message: string;
}

export type ProviderId = "openai" | "anthropic" | "gemini" | "groq" | "ollama";

export interface AIStatus {
  ok: boolean;
  provider: ProviderId | "";
  provider_name: string;
  model: string;
  model_label: string;
  message: string;
}

/** Never contains an API key - only whether one is saved and its last 4 characters. */
export interface ProviderSummary {
  id: ProviderId;
  name: string;
  tagline: string;
  needs_key: boolean;
  key_url: string;
  key_placeholder: string;
  key_set: boolean;
  key_ending: string;
  /** has a saved key, or (local AI) is running with a model */
  available?: boolean;
}

export interface ProviderDetail extends ProviderSummary {
  ready: boolean;
  models: { id: string; label: string }[];
  model: string;
  message: string;
}

export interface Settings {
  ai: {
    provider: ProviderId | "";
    models: Record<ProviderId, string>;
    ollama_url: string;
    temperature: number;
    context_chars: number;
  };
  web: { max_pages: number; respect_robots: boolean; render: "auto" | "always" | "never"; delay_s: number };
  scraper: {
    headless: boolean;
    scroll_pause_ms: number;
    max_posts: number;
    max_comments_per_post: number;
    default_range_days: number;
  };
  ui: { theme: "system" | "light" | "dark"; accent: "violet" | "blue" | "emerald" | "rose" | "amber" | "graphite" };
}

export interface Chat {
  id: number;
  dataset_id: number;
  title: string;
  created_at: number;
}

export interface MessageMeta {
  model?: string;
  provider?: string;
  provider_name?: string;
  refs_used?: number[];
  complete?: boolean;
  cached?: boolean;
  ttft_ms?: number;
  total_ms?: number;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta: MessageMeta | null;
  created_at: number;
}

export type AskEvent =
  | ({ type: "meta" } & MessageMeta)
  | { type: "token"; text: string }
  | { type: "done"; meta?: MessageMeta }
  | { type: "error"; message: string };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : j.detail?.[0]?.msg || msg;
    } catch {
      /* not json */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  status: () => req<{ version: string; facebook: FacebookState; jobs: Job[] }>("/api/status"),
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (patch: unknown) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),

  fbStatus: (refresh = false) => req<FacebookState>(`/api/facebook/status${refresh ? "?refresh=true" : ""}`),
  fbLogin: () => req<FacebookState>("/api/facebook/login", { method: "POST" }),
  fbLogout: () => req<FacebookState>("/api/facebook/logout", { method: "POST" }),

  aiStatus: () => req<AIStatus>("/api/ai/status"),
  providers: () =>
    req<{ active: ProviderId | ""; storage: "vault" | "file"; providers: ProviderSummary[]; local_supported: boolean }>("/api/ai/providers"),
  provider: (id: ProviderId) => req<ProviderDetail>(`/api/ai/providers/${id}`),
  /** The key travels once, to this app on 127.0.0.1, which verifies it and stores it in the OS vault. */
  saveKey: (id: ProviderId, api_key: string) =>
    req<ProviderDetail>(`/api/ai/providers/${id}/key`, { method: "PUT", body: JSON.stringify({ api_key }) }),
  removeKey: (id: ProviderId) => req<ProviderDetail>(`/api/ai/providers/${id}/key`, { method: "DELETE" }),

  datasets: () => req<Dataset[]>("/api/datasets"),
  dataset: (id: number) => req<Dataset>(`/api/datasets/${id}`),
  startScrape: (body: { url: string; range_days?: number; max_posts?: number; mode?: "page" | "site"; max_pages?: number }) =>
    req<{ id: number }>("/api/datasets", { method: "POST", body: JSON.stringify(body) }),
  pages: (id: number) => req<PageRow[]>(`/api/datasets/${id}/pages`),
  siteOverview: (id: number) => req<SiteOverview>(`/api/datasets/${id}/overview`),
  warm: (id: number) => req<{ warming: boolean }>(`/api/datasets/${id}/warm`, { method: "POST" }),
  local: () => req<LocalStatus>("/api/local"),
  localPull: (model: string) => req<LocalStatus["pull"]>("/api/local/pull", { method: "POST", body: JSON.stringify({ model }) }),
  localPullState: () => req<LocalStatus["pull"]>("/api/local/pull"),
  localUse: (model: string) => req<LocalStatus>("/api/local/use", { method: "POST", body: JSON.stringify({ model }) }),
  localCheckUpdates: () => req<LocalStatus>("/api/local/check-updates", { method: "POST" }),
  demo: () => req<{ id: number }>("/api/demo", { method: "POST" }),
  deleteDataset: (id: number) => req(`/api/datasets/${id}`, { method: "DELETE" }),
  deleteAll: () => req("/api/datasets", { method: "DELETE" }),
  posts: (id: number) => req<Post[]>(`/api/datasets/${id}/posts`),
  overview: (id: number) => req<Overview>(`/api/datasets/${id}/overview`),
  job: (id: number) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: number) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),

  chats: (dsId: number) => req<Chat[]>(`/api/datasets/${dsId}/chats`),
  newChat: (dsId: number) => req<{ id: number }>(`/api/datasets/${dsId}/chats`, { method: "POST" }),
  deleteChat: (id: number) => req(`/api/chats/${id}`, { method: "DELETE" }),
  messages: (chatId: number) => req<Message[]>(`/api/chats/${chatId}/messages`),

  /** Streams newline-delimited JSON events from the model. */
  async ask(chatId: number, question: string, onEvent: (e: AskEvent) => void, signal?: AbortSignal, fresh = false) {
    const r = await fetch(`/api/chats/${chatId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, fresh }),
      signal,
    });
    if (!r.ok || !r.body) throw new Error(`Request failed (${r.status})`);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i: number;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
  },
};
