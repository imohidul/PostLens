import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  Check, ChevronDown, Cpu, Database, Download, ExternalLink, Info, Eye, EyeOff, KeyRound, Laptop, Lock, LogOut, Moon, Palette,
  RefreshCw, ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, Sun, Trash2,
} from "lucide-react";
import { api, type LocalStatus, type ProviderDetail, type ProviderId, type ProviderSummary, type Settings as S } from "../api";
import { useApp } from "../store";
import { Badge, Button, Card, Input, Segmented, Skeleton, Toggle } from "../components/ui";
import { FacebookGlyph } from "../components/Logo";
import { ACCENTS, type ThemeMode } from "../lib/theme";

type Section = "ai" | "appearance" | "facebook" | "collection" | "privacy";

const SECTIONS: { id: Section; label: string; icon: ReactNode }[] = [
  { id: "ai", label: "AI assistant", icon: <Sparkles className="size-4" /> },
  { id: "appearance", label: "Appearance", icon: <Palette className="size-4" /> },
  { id: "facebook", label: "Facebook account", icon: <FacebookGlyph className="size-4" /> },
  { id: "collection", label: "Collection", icon: <SlidersHorizontal className="size-4" /> },
  { id: "privacy", label: "Data & privacy", icon: <ShieldCheck className="size-4" /> },
];

export default function Settings() {
  const loc = useLocation();
  const nav = useNavigate();
  const section = (SECTIONS.find((s) => `#${s.id}` === loc.hash)?.id ?? "ai") as Section;
  const [s, setS] = useState<S | null>(null);

  useEffect(() => {
    api.settings().then(setS);
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-8 py-10">
      <h1 className="text-[26px] font-semibold tracking-[-0.03em]">Settings</h1>
      <p className="text-sm text-muted mt-1">Preferences are saved on this computer.</p>

      <div className="mt-8 grid grid-cols-[200px_1fr] gap-10">
        <nav className="space-y-0.5 sticky top-6 self-start">
          {SECTIONS.map((x) => (
            <button
              key={x.id}
              onClick={() => nav(`/settings#${x.id}`, { replace: true })}
              className={clsx(
                "w-full flex items-center gap-2.5 h-9 px-3 rounded-lg text-sm transition text-left",
                section === x.id ? "bg-surface-2 text-text font-medium shadow-card" : "text-muted hover:text-text hover:bg-surface-2/60",
              )}
            >
              <span className={section === x.id ? "text-accent-2" : "text-faint"}>{x.icon}</span>
              {x.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0 fade-up" key={section}>
          {!s ? (
            <Skeleton className="h-96" />
          ) : section === "ai" ? (
            <AISection s={s} setS={setS} />
          ) : section === "appearance" ? (
            <AppearanceSection />
          ) : section === "facebook" ? (
            <FacebookSection />
          ) : section === "collection" ? (
            <CollectionSection s={s} setS={setS} />
          ) : (
            <PrivacySection />
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ shared */

function Header({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold tracking-[-0.02em]">{title}</h2>
      <p className="text-sm text-muted mt-1">{desc}</p>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 px-5 py-4">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="text-[12.5px] text-muted mt-0.5 leading-relaxed">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function useSave(setS: (s: S) => void) {
  const { toast, refreshAI } = useApp();
  return useCallback(
    async (patch: unknown, msg?: string) => {
      try {
        setS(await api.saveSettings(patch));
        await refreshAI();
        if (msg) toast(msg, "success");
      } catch (e) {
        toast((e as Error).message, "error");
      }
    },
    [setS, toast, refreshAI],
  );
}

/* ------------------------------------------------------------------ AI */

function Monogram({ id, active }: { id: ProviderId; active?: boolean }) {
  const letter = { openai: "O", anthropic: "A", gemini: "G", groq: "Gq", ollama: "" }[id];
  return (
    <div
      className={clsx(
        "size-10 rounded-xl grid place-items-center text-[15px] font-semibold tracking-[-0.02em] border transition",
        active ? "bg-accent text-accent-ink border-transparent" : "bg-surface-2 text-text border-line-strong",
      )}
    >
      {id === "ollama" ? <Laptop className="size-[18px]" /> : letter}
    </div>
  );
}

const PRODUCT: Record<ProviderId, string> = {
  openai: "ChatGPT",
  anthropic: "Claude",
  gemini: "Gemini",
  groq: "Groq",
  ollama: "Local AI",
};

const DEPTH = [
  { value: 12000, label: "Focused", hint: "Fastest. Reads the most relevant posts only." },
  { value: 24000, label: "Balanced", hint: "Good for most pages." },
  { value: 60000, label: "Thorough", hint: "Reads more comments per answer. Slower and uses more of your API quota." },
];

function AISection({ s, setS }: { s: S; setS: (s: S) => void }) {
  const save = useSave(setS);
  const [list, setList] = useState<ProviderSummary[] | null>(null);
  const [storage, setStorage] = useState<"vault" | "file">("vault");
  const [selected, setSelected] = useState<ProviderId | "">(s.ai.provider);
  const [localOk, setLocalOk] = useState(true);

  const reload = useCallback(async () => {
    const r = await api.providers();
    setList(r.providers);
    setStorage(r.storage);
    setLocalOk(r.local_supported);
    setSelected((cur) => (r.providers.some((p) => p.id === cur) ? cur : r.providers[0]?.id ?? ""));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  const active = s.ai.provider;
  const depth = DEPTH.reduce((best, d) => (Math.abs(d.value - s.ai.context_chars) < Math.abs(best.value - s.ai.context_chars) ? d : best));

  return (
    <div>
      <Header title="AI assistant" desc="Choose which AI answers your questions. You can switch at any time; your chats stay." />

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {(list || Array.from({ length: 5 }).map(() => null)).map((p, i) =>
          !p ? (
            <Skeleton key={i} className="h-[92px] rounded-xl" />
          ) : (
            <button
              key={p.id}
              onClick={() => setSelected(p.id)}
              className={clsx(
                "relative text-left rounded-xl border p-4 flex gap-3 items-start transition",
                selected === p.id ? "border-accent/60 bg-surface ring-4 ring-accent-soft" : "border-line bg-surface hover:border-line-strong",
              )}
            >
              <Monogram id={p.id} active={active === p.id} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{PRODUCT[p.id]}</div>
                <div className="text-[12px] text-muted truncate">{p.id === "ollama" ? "Free & private" : `by ${p.name}`}</div>
                <div className="mt-2">
                  {active === p.id ? (
                    <Badge tone="accent" dot>In use</Badge>
                  ) : p.available ? (
                    <Badge tone="success" dot>{p.needs_key ? "Connected" : "Available"}</Badge>
                  ) : (
                    <Badge>Not set up</Badge>
                  )}
                </div>
              </div>
            </button>
          ),
        )}
      </div>

      {list && !localOk && <LocalUnavailable />}

      {list && selected && list.some((p) => p.id === selected) && (
        <ProviderPanel
          key={selected}
          summary={list.find((p) => p.id === selected)!}
          settings={s}
          storage={storage}
          isActive={active === selected}
          onUse={() => save({ ai: { provider: selected } }, `${PRODUCT[selected as ProviderId]} is now answering your questions`)}
          onModel={(m) => save({ ai: { models: { [selected]: m } } }, "Model updated")}
          onOllamaUrl={(u) => save({ ai: { ollama_url: u } }, "Saved")}
          onChanged={reload}
        />
      )}

      <Card className="mt-6">
        <div className="px-5 pt-5">
          <div className="text-sm font-medium">Reading depth</div>
          <div className="text-[12.5px] text-muted mt-0.5">How much of the collected text the AI reads for each answer.</div>
        </div>
        <div className="px-5 pb-5 pt-4 flex flex-wrap items-center gap-4">
          <Segmented
            value={depth.value}
            onChange={(v) => save({ ai: { context_chars: v } }, "Saved")}
            options={DEPTH.map((d) => ({ value: d.value, label: d.label }))}
          />
          <span className="text-[12.5px] text-muted">{depth.hint}</span>
        </div>
      </Card>
    </div>
  );
}

function ProviderPanel({
  summary, settings, storage, isActive, onUse, onModel, onOllamaUrl, onChanged,
}: {
  summary: ProviderSummary;
  settings: S;
  storage: "vault" | "file";
  isActive: boolean;
  onUse: () => void;
  onModel: (m: string) => void;
  onOllamaUrl: (u: string) => void;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const [d, setD] = useState<ProviderDetail | null>(null);
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.provider(summary.id).then((r) => { setD(r); onChanged(); }), [summary.id, onChanged]);
  useEffect(() => {
    load();
  }, [load]);

  const verify = async () => {
    setBusy(true);
    try {
      const r = await api.saveKey(summary.id, key);
      setD(r);
      setKey("");
      setEditing(false);
      onChanged();
      toast(`${PRODUCT[summary.id]} connected. Key verified and stored securely.`, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm(`Remove your ${summary.name} API key from this computer?`)) return;
    setD(await api.removeKey(summary.id));
    onChanged();
    toast("Key removed", "success");
  };

  const vaultName = storage === "vault" ? "your system's secure credential store" : "a protected file in your user folder";
  const local = summary.id === "ollama";
  const hasKey = !!d?.key_set;
  const canUse = local ? !!d?.ready : hasKey && !!d?.ready;

  return (
    <Card className="mt-4 overflow-hidden">
      <div className="px-6 py-5 flex items-center gap-4 border-b border-line">
        <Monogram id={summary.id} active={isActive} />
        <div className="flex-1 min-w-0">
          <div className="font-semibold">{local ? "Local AI on this computer" : `${PRODUCT[summary.id]} by ${summary.name}`}</div>
          <div className="text-[13px] text-muted">
            {local
              ? "Runs entirely on your PC. Free, private, works offline. Needs a reasonably modern computer."
              : `Uses your own ${summary.name} account. Usage is billed by ${summary.name} according to your plan.`}
          </div>
        </div>
        {isActive ? (
          <Badge tone="accent" dot>In use</Badge>
        ) : (
          <Button variant="primary" size="sm" disabled={!canUse} onClick={onUse}>
            Use {PRODUCT[summary.id]}
          </Button>
        )}
      </div>

      <div className="px-6 py-5 space-y-5">
        {!d ? (
          <Skeleton className="h-20" />
        ) : local ? (
          <LocalManager ollamaUrl={settings.ai.ollama_url} onOllamaUrl={onOllamaUrl} onChanged={load} />
        ) : hasKey && !editing ? (
          <div className="flex items-center gap-4 rounded-xl border border-line bg-surface-2/50 px-4 py-3">
            <div className="size-9 rounded-lg bg-success/10 text-success grid place-items-center">
              <KeyRound className="size-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">API key connected</div>
              <div className="text-[12.5px] text-muted font-mono tracking-wide">••••••••••••{d.key_ending}</div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Replace</Button>
            <Button size="sm" variant="danger" icon={<Trash2 className="size-3.5" />} onClick={remove}>Remove</Button>
          </div>
        ) : (
          <div>
            <label className="text-sm font-medium" htmlFor="api-key">API key</label>
            <div className="mt-2 flex gap-2">
              <div className="relative flex-1">
                <KeyRound className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
                <Input
                  id="api-key"
                  type={show ? "text" : "password"}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && key.length >= 8 && verify()}
                  placeholder={summary.key_placeholder ? `Paste your key (${summary.key_placeholder})` : "Paste your key"}
                  className="pl-9 pr-10 font-mono"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-faint hover:text-text"
                  aria-label={show ? "Hide key" : "Show key"}
                >
                  {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              <Button variant="primary" loading={busy} disabled={key.trim().length < 8} onClick={verify}>
                Verify &amp; save
              </Button>
              {editing && <Button variant="ghost" onClick={() => { setEditing(false); setKey(""); }}>Cancel</Button>}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-[12.5px]">
              <a href={summary.key_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-2 hover:underline">
                Get a {summary.name} API key <ExternalLink className="size-3" />
              </a>
            </div>
          </div>
        )}

        {!local && (
          <div className="flex gap-3 rounded-xl bg-surface-2/50 border border-line px-4 py-3 text-[12.5px] text-muted leading-relaxed">
            <Lock className="size-4 text-faint shrink-0 mt-0.5" />
            <span>
              Your key is checked with {summary.name}, then kept in {vaultName}. PostLens never shows it again, never
              writes it to the project folder, and never includes it in exports. It is only ever sent to {summary.name}.
            </span>
          </div>
        )}

        {d && d.models.length > 0 && !local && (
          <ModelSelect models={d.models} value={d.model} onChange={(m) => { onModel(m); setD({ ...d, model: m }); }} />
        )}

      </div>
    </Card>
  );
}

function ModelSelect({ models, value, onChange }: { models: { id: string; label: string }[]; value: string; onChange: (m: string) => void }) {
  return (
    <div>
      <label className="text-sm font-medium">Model</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 h-10 w-full rounded-lg bg-surface-2 border border-line-strong px-3 text-sm focus:outline-none focus:border-accent"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>
      <p className="text-[12px] text-faint mt-1.5">We pick a balanced model automatically. Change it only if you have a preference.</p>
    </div>
  );
}

function LocalUnavailable() {
  const [open, setOpen] = useState(false);
  const [st, setSt] = useState<LocalStatus | null>(null);
  useEffect(() => {
    if (open && !st) api.local().then(setSt).catch(() => {});
  }, [open, st]);
  return (
    <div className="mt-3">
      <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1.5 text-[12.5px] text-muted hover:text-text">
        <Info className="size-3.5" /> Why isn't Local AI available on this computer?
        <ChevronDown className={clsx("size-3.5 transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 rounded-xl border border-line bg-surface-2/50 p-4 text-[13px] text-muted leading-relaxed fade-up">
          <p>
            Local AI runs the model on your own computer. To keep answers fast and high-quality, PostLens only offers it on computers
            with a dedicated graphics card or Apple Silicon:
          </p>
          <ul className="mt-2 list-disc pl-5 space-y-0.5">
            <li>Windows / Linux: NVIDIA or AMD graphics card with 8 GB+ video memory, and 16 GB+ RAM</li>
            <li>Mac: Apple Silicon (M1 or newer) with 16 GB+ memory</li>
            <li>20 GB+ free disk space</li>
          </ul>
          {st && st.reasons.length > 0 && (
            <div className="mt-3 text-text">
              This computer: {st.reasons.join(" ")}
            </div>
          )}
          <p className="mt-2">You can use ChatGPT, Claude, Gemini or Groq instead. They work on any computer.</p>
        </div>
      )}
    </div>
  );
}

function fmtGB(bytes: number) {
  return (bytes / 1024 ** 3).toFixed(1);
}

function LocalManager({ ollamaUrl, onOllamaUrl, onChanged }: { ollamaUrl: string; onOllamaUrl: (u: string) => void; onChanged: () => void }) {
  const { toast, refreshAI } = useApp();
  const [st, setSt] = useState<LocalStatus | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    const r = await api.local();
    setSt(r);
    return r;
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  // poll while a download runs
  useEffect(() => {
    if (st?.pull.status !== "downloading") return;
    const t = setInterval(async () => {
      const p = await api.localPullState();
      setSt((cur) => (cur ? { ...cur, pull: p } : cur));
      if (p.status !== "downloading") {
        clearInterval(t);
        const r = await load();
        if (p.status === "done" && p.model) {
          await api.localUse(p.model);
          await refreshAI();
          onChanged();
          toast(`${r.allowed.find((m) => m.model === p.model)?.name ?? "Model"} is ready`, "success");
        } else if (p.error) toast(p.error, "error");
      }
    }, 1000);
    return () => clearInterval(t);
  }, [st?.pull.status, load, onChanged, refreshAI, toast]);

  if (!st) return <Skeleton className="h-28" />;

  const hwText = st.hardware.apple_silicon
    ? `Apple Silicon · ${st.hardware.ram_gb.toFixed(0)} GB memory`
    : `${st.hardware.gpus.find((g) => g.vram_gb === st.hardware.vram_gb)?.name ?? "Graphics card"} · ${st.hardware.vram_gb} GB video memory · ${st.hardware.ram_gb.toFixed(0)} GB RAM`;
  const rec = st.recommended!;
  const recInstalled = st.installed.some((m) => m.model === rec.model);
  const downloading = st.pull.status === "downloading";
  const pct = st.pull.total ? Math.round((st.pull.completed / st.pull.total) * 100) : 0;

  const download = async (model: string) => {
    try {
      const p = await api.localPull(model);
      setSt({ ...st, pull: p });
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const use = async (model: string) => {
    setSt(await api.localUse(model));
    await refreshAI();
    onChanged();
    toast("Local model switched", "success");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-2/50 px-4 py-3">
        <div className="size-9 rounded-lg bg-accent-soft text-accent-2 grid place-items-center"><Cpu className="size-4" /></div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">Your computer qualifies for the {st.tier?.label} tier</div>
          <div className="text-[12.5px] text-muted truncate">{hwText}</div>
        </div>
      </div>

      {!st.running ? (
        <div className="rounded-xl border border-line bg-surface-2/50 p-4">
          <div className="text-sm font-medium">Install the local AI engine</div>
          <p className="mt-1 text-[13px] text-muted">
            PostLens uses the free Ollama app to run models on your computer. Install it from{" "}
            <a href="https://ollama.com/download" target="_blank" rel="noreferrer" className="text-accent-2 hover:underline">ollama.com/download</a>,
            open it, then check again. PostLens downloads the right model for you.
          </p>
          <Button size="sm" className="mt-3" icon={<RefreshCw className="size-3.5" />} onClick={load}>Check again</Button>
        </div>
      ) : (
        <>
          {st.update_available && recInstalled === false && !downloading && (
            <div className="flex items-center gap-3 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-[13px]">
              <Sparkles className="size-4 text-accent-2 shrink-0" />
              <span className="flex-1">A better model for your computer is available: <b>{rec.name}</b>.</span>
            </div>
          )}
          <div className="rounded-xl border border-line p-4">
            <div className="flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{rec.name}</span>
                  <Badge tone="accent">Recommended</Badge>
                </div>
                <p className="text-[12.5px] text-muted mt-1 leading-relaxed">{rec.why}</p>
                <p className="text-[12px] text-faint mt-1">{rec.download_gb} GB download · reads up to {Math.round(rec.num_ctx / 1000)}k tokens at once</p>
              </div>
              {st.active?.model === rec.model ? (
                <Badge tone="success" dot>In use</Badge>
              ) : recInstalled ? (
                <Button size="sm" variant="primary" onClick={() => use(rec.model)}>Use</Button>
              ) : (
                <Button size="sm" variant="primary" loading={downloading && st.pull.model === rec.model} disabled={downloading}
                        icon={<Download className="size-3.5" />} onClick={() => download(rec.model)}>
                  Download
                </Button>
              )}
            </div>
            {downloading && (
              <div className="mt-4">
                <div className="flex justify-between text-[12px] text-muted">
                  <span>Downloading {st.allowed.find((m) => m.model === st.pull.model)?.name}…</span>
                  <span className="tabular-nums">{st.pull.total ? `${fmtGB(st.pull.completed)} / ${fmtGB(st.pull.total)} GB · ${pct}%` : "Starting…"}</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                  <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )}
          </div>
        </>
      )}

      <div>
        <button onClick={() => setAdvanced(!advanced)} className="flex items-center gap-1.5 text-[13px] text-muted hover:text-text">
          <ChevronDown className={clsx("size-4 transition", advanced && "rotate-180")} /> Advanced
        </button>
        {advanced && (
          <div className="mt-3 space-y-4 fade-up">
            {st.allowed.length > 1 && (
              <div>
                <div className="text-sm font-medium mb-2">Other models for your computer</div>
                <div className="space-y-2">
                  {st.allowed.filter((m) => m.model !== rec.model).map((m) => {
                    const inst = st.installed.some((x) => x.model === m.model);
                    return (
                      <div key={m.model} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-[13px] font-medium">{m.name} <span className="text-faint font-normal">· {m.label} tier · {m.download_gb} GB</span></div>
                        </div>
                        {st.active?.model === m.model ? <Badge tone="success" dot>In use</Badge>
                          : inst ? <Button size="sm" onClick={() => use(m.model)}>Use</Button>
                          : <Button size="sm" disabled={downloading} onClick={() => download(m.model)}>Download</Button>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <div className="flex items-center justify-between gap-3">
              <div className="text-[12.5px] text-muted">Model recommendations: version {st.catalog_version}</div>
              <Button size="sm" variant="ghost" loading={checking} icon={<RefreshCw className="size-3.5" />}
                      onClick={async () => {
                        setChecking(true);
                        try {
                          const r = await api.localCheckUpdates();
                          setSt(r);
                          toast(r.updated ? "New model recommendations downloaded" : "You have the latest recommendations", "success");
                        } finally {
                          setChecking(false);
                        }
                      }}>
                Check for updates
              </Button>
            </div>
            <div>
              <div className="text-sm font-medium mb-2">Service address</div>
              <Input defaultValue={ollamaUrl} onBlur={(e) => e.target.value !== ollamaUrl && onOllamaUrl(e.target.value)} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Appearance */

function ThemePreview({ mode }: { mode: "light" | "dark" | "system" }) {
  const pane = (dark: boolean) => (
    <div className={clsx("h-full flex", dark ? "bg-[#0b0b0e]" : "bg-[#f4f4f6]")}>
      <div className={clsx("w-1/4 border-r", dark ? "bg-[#131317] border-white/5" : "bg-white border-black/5")} />
      <div className="flex-1 p-2 space-y-1.5">
        <div className={clsx("h-2 w-1/2 rounded-full", dark ? "bg-white/25" : "bg-black/20")} />
        <div className={clsx("h-6 rounded-md", dark ? "bg-[#1a1a20]" : "bg-white shadow-sm")} />
        <div className="h-2 w-1/3 rounded-full bg-accent" />
      </div>
    </div>
  );
  return (
    <div className="h-24 rounded-lg overflow-hidden border border-line">
      {mode === "system" ? (
        <div className="h-full grid grid-cols-2">{pane(false)}{pane(true)}</div>
      ) : (
        pane(mode === "dark")
      )}
    </div>
  );
}

function AppearanceSection() {
  const { themeMode, setThemeMode, accent, setAccent, theme } = useApp();
  const modes: { id: ThemeMode; label: string; icon: ReactNode }[] = [
    { id: "system", label: "System", icon: <Laptop className="size-4" /> },
    { id: "light", label: "Light", icon: <Sun className="size-4" /> },
    { id: "dark", label: "Dark", icon: <Moon className="size-4" /> },
  ];
  return (
    <div>
      <Header title="Appearance" desc="Make PostLens look the way you like. Changes apply instantly." />
      <Card className="p-5">
        <div className="text-sm font-medium">Theme</div>
        <div className="text-[12.5px] text-muted mt-0.5">System follows your computer's light or dark setting.</div>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {modes.map((m) => (
            <button
              key={m.id}
              onClick={() => setThemeMode(m.id)}
              className={clsx(
                "rounded-xl border p-2.5 text-left transition",
                themeMode === m.id ? "border-accent/60 ring-4 ring-accent-soft" : "border-line hover:border-line-strong",
              )}
            >
              <ThemePreview mode={m.id} />
              <div className="mt-2.5 px-1 flex items-center gap-2 text-sm font-medium">
                <span className="text-faint">{m.icon}</span>
                {m.label}
                {themeMode === m.id && <Check className="size-4 ml-auto text-accent-2" />}
              </div>
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-5 mt-4">
        <div className="text-sm font-medium">Accent color</div>
        <div className="text-[12.5px] text-muted mt-0.5">Used for buttons, highlights and charts.</div>
        <div className="mt-4 flex flex-wrap gap-3">
          {ACCENTS.map((a) => (
            <button
              key={a.id}
              onClick={() => setAccent(a.id)}
              className={clsx(
                "flex items-center gap-2.5 h-10 pl-2 pr-3.5 rounded-xl border text-sm transition",
                accent === a.id ? "border-accent/60 ring-4 ring-accent-soft font-medium" : "border-line hover:border-line-strong text-muted hover:text-text",
              )}
              aria-pressed={accent === a.id}
            >
              <span
                className="size-6 rounded-lg grid place-items-center border border-black/10"
                style={{ background: theme === "dark" ? a.dark : a.light }}
              >
                {accent === a.id && <Check className="size-3.5" style={{ color: a.id === "graphite" && theme === "dark" ? "#09090b" : "#fff" }} />}
              </span>
              {a.label}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ Facebook */

function FacebookSection() {
  const { facebook, setFacebook, refreshFacebook } = useApp();
  return (
    <div>
      <Header title="Facebook account" desc="PostLens reads Facebook through its own browser window, signed in as you." />
      <Card>
        <div className="flex items-center gap-4 p-5">
          <div className="size-10 rounded-xl bg-[#1877F2]/10 grid place-items-center text-[#1877F2]">
            <FacebookGlyph className="size-5" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium">
              {facebook?.logged_in ? "Connected" : facebook?.login_running ? "Waiting for you to sign in…" : facebook?.checking ? "Checking…" : "Not connected"}
            </div>
            <div className="text-[13px] text-muted">{facebook?.message || "You sign in on Facebook's own page. PostLens never sees your password."}</div>
          </div>
          {facebook?.logged_in ? (
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => refreshFacebook(true)}>Verify</Button>
              <Button size="sm" variant="danger" icon={<LogOut className="size-3.5" />} onClick={async () => setFacebook(await api.fbLogout())}>Disconnect</Button>
            </div>
          ) : (
            <Button variant="primary" size="sm" loading={facebook?.login_running} onClick={async () => setFacebook(await api.fbLogin())}>Connect</Button>
          )}
        </div>
      </Card>
      <div className="mt-4 flex gap-3 rounded-xl border border-warning/20 bg-warning/5 p-4 text-[13px] text-muted leading-relaxed">
        <ShieldAlert className="size-4 text-warning shrink-0 mt-0.5" />
        <span>
          Facebook's terms don't allow automated collection without permission, and heavy use can get an account restricted.
          Consider a secondary account, keep date ranges small, and only analyze content you're allowed to.
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Collection */

function CollectionSection({ s, setS }: { s: S; setS: (s: S) => void }) {
  const save = useSave(setS);
  const pace = useMemo(
    () => [
      { value: 1200, label: "Faster" },
      { value: 1800, label: "Balanced" },
      { value: 3000, label: "Careful" },
    ],
    [],
  );
  const current = pace.reduce((b, p) => (Math.abs(p.value - s.scraper.scroll_pause_ms) < Math.abs(b.value - s.scraper.scroll_pause_ms) ? p : b));
  return (
    <div>
      <Header title="Collection" desc="How PostLens reads websites and Facebook pages." />
      <Card className="divide-y divide-line">
        <Row label="Show browser window" hint="Lets you watch what happens. A visible window also behaves more like a real person.">
          <Toggle checked={!s.scraper.headless} onChange={(v) => save({ scraper: { headless: !v } }, "Saved")} />
        </Row>
        <Row label="Pace" hint="Pause between scrolls and clicks.">
          <Segmented value={current.value} onChange={(v) => save({ scraper: { scroll_pause_ms: v } }, "Saved")} options={pace} />
        </Row>
        <Row label="Comments per post" hint="Maximum comments to read from each post.">
          <select
            value={s.scraper.max_comments_per_post}
            onChange={(e) => save({ scraper: { max_comments_per_post: Number(e.target.value) } }, "Saved")}
            className="h-9 rounded-lg bg-surface-2 border border-line-strong px-2.5 text-sm"
          >
            {[50, 100, 150, 300, 500].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </Card>
      <div className="mt-6 mb-2 text-sm font-semibold">Websites</div>
      <Card className="divide-y divide-line">
        <Row label="JavaScript sites" hint="Auto uses a real browser only when a page needs it, which is fastest. Always is slower but thorough.">
          <Segmented
            value={s.web.render}
            onChange={(v) => save({ web: { render: v } }, "Saved")}
            options={[{ value: "auto", label: "Auto" }, { value: "always", label: "Always" }, { value: "never", label: "Never" }]}
          />
        </Row>
        <Row label="Politeness delay" hint="Pause between requests to the same site. PostLens always follows robots.txt.">
          <Segmented
            value={s.web.delay_s}
            onChange={(v) => save({ web: { delay_s: v } }, "Saved")}
            options={[{ value: 0.25, label: "0.25s" }, { value: 0.5, label: "0.5s" }, { value: 1, label: "1s" }, { value: 2, label: "2s" }]}
          />
        </Row>
      </Card>
      <div className="mt-6 mb-2 text-sm font-semibold">Facebook</div>
    </div>
  );
}

/* ------------------------------------------------------------------ Privacy */

function PrivacySection() {
  const { refreshDatasets, toast } = useApp();
  const [storage, setStorage] = useState<"vault" | "file" | null>(null);
  useEffect(() => {
    api.providers().then((r) => setStorage(r.storage)).catch(() => {});
  }, []);
  const facts = [
    { t: "No names collected", d: "Author names, profile links, photos and IDs are never read. Tagged names, emails and phone numbers in text are removed." },
    { t: "Stays on this computer", d: "Collected data is saved locally. The app only accepts connections from this computer." },
    {
      t: "API keys are locked away",
      d:
        storage === "file"
          ? "No secure credential store was found, so keys are kept in a protected file in your user folder, never in the project folder."
          : "Keys are kept in your system's secure credential store (Windows Credential Manager or macOS Keychain) and are never shown, exported or written to the project folder.",
    },
    { t: "AI sees only anonymized text", d: "When you use a cloud AI, only the already-anonymized posts and comments needed for your question are sent." },
  ];
  return (
    <div>
      <Header title="Data & privacy" desc="What PostLens stores and where." />
      <div className="grid sm:grid-cols-2 gap-3">
        {facts.map((f) => (
          <div key={f.t} className="rounded-xl border border-line bg-surface p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="size-4 text-success" /> {f.t}
            </div>
            <p className="text-[12.5px] text-muted mt-1.5 leading-relaxed">{f.d}</p>
          </div>
        ))}
      </div>
      <Card className="mt-6">
        <Row label="Delete all analyses" hint="Removes every collected post, comment and chat from this computer.">
          <Button
            variant="danger"
            size="sm"
            icon={<Database className="size-3.5" />}
            onClick={async () => {
              if (!confirm("Delete ALL collected data and chats? This can't be undone.")) return;
              await api.deleteAll();
              await refreshDatasets();
              toast("All data deleted", "success");
            }}
          >
            Delete all
          </Button>
        </Row>
      </Card>
    </div>
  );
}
