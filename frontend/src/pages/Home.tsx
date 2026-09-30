import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, BarChart3, CheckCircle2, CircleDashed, FlaskConical, Globe, Lock, ShieldCheck, Sparkles, Zap,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../api";
import { useApp } from "../store";
import { Button, Segmented } from "../components/ui";
import { FacebookGlyph } from "../components/Logo";
import { RANGES } from "../lib/format";

function isFacebook(url: string) {
  try {
    const u = new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`);
    return /(^|\.)(facebook\.com|fb\.com)$/i.test(u.hostname);
  } catch {
    return false;
  }
}

export default function Home() {
  const { facebook, ai, refreshDatasets, toast, refreshFacebook, setFacebook } = useApp();
  const nav = useNavigate();
  const [url, setUrl] = useState("");
  const [range, setRange] = useState(30);
  const [maxPosts, setMaxPosts] = useState(60);
  const [mode, setMode] = useState<"site" | "page">("site");
  const [maxPages, setMaxPages] = useState(30);
  const [busy, setBusy] = useState(false);

  const fb = useMemo(() => isFacebook(url.trim()), [url]);
  const fbReady = !!facebook?.logged_in;

  const start = async () => {
    if (!url.trim()) return toast("Paste a website or Facebook link first.", "error");
    if (fb && !fbReady) return toast("Connect your Facebook account first.", "error");
    setBusy(true);
    try {
      const { id } = await api.startScrape(
        fb ? { url: url.trim(), range_days: range, max_posts: maxPosts } : { url: url.trim(), mode, max_pages: maxPages },
      );
      await refreshDatasets();
      nav(`/d/${id}`);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const demo = async () => {
    const { id } = await api.demo();
    await refreshDatasets();
    nav(`/d/${id}`);
  };

  const connect = async () => {
    setFacebook(await api.fbLogin());
    toast("A browser window opened. Sign in to Facebook there, then come back.", "info");
    setTimeout(() => refreshFacebook(), 1500);
  };

  return (
    <div className="relative min-h-full">
      <div className="absolute inset-x-0 top-0 h-[420px] hero-glow pointer-events-none" />
      <div className="absolute inset-x-0 top-0 h-[420px] grid-bg pointer-events-none opacity-60" />

      <div className="relative max-w-3xl mx-auto px-8 pt-20 pb-16">
        <div className="fade-up flex justify-center">
          <span className="inline-flex items-center gap-2 h-7 px-3 rounded-full border border-line-strong bg-surface/70 backdrop-blur text-[12px] text-muted">
            <Sparkles className="size-3.5 text-accent-2" /> Websites & Facebook pages · runs on your computer
          </span>
        </div>
        <h1 className="fade-up mt-6 text-center text-[44px] leading-[1.05] font-semibold tracking-[-0.035em] text-gradient">
          Understand any website
          <br /> in minutes, not hours.
        </h1>
        <p className="fade-up mt-4 text-center text-[15px] text-muted max-w-xl mx-auto">
          Paste a link. PostLens reads the pages (or a Facebook page's posts and comments), shows what stands out,
          and answers your questions in seconds.
        </p>

        {/* Composer */}
        <div className="fade-up mt-10 rounded-2xl border border-line-strong bg-surface shadow-card p-2 focus-within:ring-4 focus-within:ring-accent-soft focus-within:border-accent/60 transition">
          <div className="flex items-center gap-3 pl-3">
            {fb ? <FacebookGlyph className="size-5 text-[#1877F2] shrink-0" /> : <Globe className="size-5 text-faint shrink-0" />}
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
              placeholder="https://example.com  or  a Facebook page link"
              className="flex-1 h-12 bg-transparent text-[15px] placeholder:text-faint focus:outline-none"
              autoFocus
            />
            <Button variant="primary" size="lg" loading={busy} onClick={start}>
              Analyze <ArrowRight className="size-4" />
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-line mt-2 pt-2 px-2 pb-0.5">
            {fb ? (
              <>
                <span className="text-[12px] text-faint">Posts from the last</span>
                <Segmented value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r.days, label: r.label }))} />
                <span className="text-[12px] text-faint ml-auto">Max posts</span>
                <Select value={maxPosts} onChange={setMaxPosts} options={[20, 40, 60, 100, 200]} />
              </>
            ) : (
              <>
                <span className="text-[12px] text-faint">Read</span>
                <Segmented
                  value={mode}
                  onChange={setMode}
                  options={[
                    { value: "site", label: "Whole website" },
                    { value: "page", label: "This page only" },
                  ]}
                />
                {mode === "site" && (
                  <>
                    <span className="text-[12px] text-faint ml-auto">Up to</span>
                    <Select value={maxPages} onChange={setMaxPages} options={[10, 30, 60, 100, 200]} suffix="pages" />
                  </>
                )}
              </>
            )}
          </div>
        </div>
        {fb && range >= 90 && (
          <p className="mt-3 text-center text-[12px] text-warning/90">
            Long ranges take a while and mean more scrolling on your account. Facebook may limit very heavy use.
          </p>
        )}

        {/* Readiness */}
        <div className={clsx("fade-up mt-8 grid gap-3", fb ? "sm:grid-cols-2" : "sm:grid-cols-1 max-w-md mx-auto")}>
          {fb && (
            <ReadyCard
              done={fbReady}
              pending={!!facebook?.checking || !!facebook?.login_running}
              title="Facebook account"
              doneText="Connected. Your session stays on this PC."
              todoText="Sign in once in a window PostLens opens. Your password never touches PostLens."
              action={
                !fbReady && (
                  <Button size="sm" variant="primary" onClick={connect} loading={!!facebook?.login_running}>
                    {facebook?.login_running ? "Waiting…" : "Connect"}
                  </Button>
                )
              }
            />
          )}
          <ReadyCard
            done={!!ai?.ok}
            title="AI assistant"
            doneText={`${ai?.provider_name} is ready to answer questions.`}
            todoText="Connect ChatGPT, Claude, Gemini or Groq with your API key, or use Local AI if your computer supports it."
            action={!ai?.ok && <Button size="sm" onClick={() => nav("/settings#ai")}>Set up</Button>}
          />
        </div>

        <div className="mt-6 flex justify-center">
          <button onClick={demo} className="inline-flex items-center gap-2 text-[13px] text-muted hover:text-text transition">
            <FlaskConical className="size-4" /> Explore with sample data
          </button>
        </div>

        <div className="mt-16 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { icon: <Globe className="size-4" />, t: "Any website", d: "Reads the sitemap, skips menus and ads, and handles JavaScript-heavy sites." },
            { icon: <BarChart3 className="size-4" />, t: "Instant overview", d: "Topics, structure and SEO issues for sites; activity and themes for Facebook." },
            { icon: <Zap className="size-4" />, t: "Fast answers", d: "Pre-built search index and prompt caching, so replies start in seconds." },
            { icon: <ShieldCheck className="size-4" />, t: "Private by design", d: "No names collected. Emails and phone numbers are removed." },
          ].map((f) => (
            <div key={f.t} className="rounded-xl p-4 border border-line bg-surface/50">
              <div className="size-8 rounded-lg bg-accent-soft text-accent-2 grid place-items-center">{f.icon}</div>
              <div className="mt-3 text-sm font-medium">{f.t}</div>
              <div className="mt-1 text-[13px] text-muted leading-relaxed">{f.d}</div>
            </div>
          ))}
        </div>
        <p className="mt-10 flex items-center justify-center gap-1.5 text-[12px] text-faint text-center">
          <Lock className="size-3 shrink-0" /> Only analyze content you're allowed to. PostLens follows each site's robots.txt rules.
        </p>
      </div>
    </div>
  );
}

function Select({ value, onChange, options, suffix }: { value: number; onChange: (v: number) => void; options: number[]; suffix?: string }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-8 rounded-md bg-surface-2 border border-line px-2 text-[13px] focus:outline-none focus:border-accent"
    >
      {options.map((n) => (
        <option key={n} value={n}>
          {n} {suffix || ""}
        </option>
      ))}
    </select>
  );
}

function ReadyCard({ done, pending, title, doneText, todoText, action }: {
  done: boolean; pending?: boolean; title: string; doneText: string; todoText: string; action?: React.ReactNode;
}) {
  return (
    <div className={clsx("rounded-xl border p-4 flex gap-3 items-start", done ? "border-line bg-surface/60" : "border-line-strong bg-surface")}>
      {done ? (
        <CheckCircle2 className="size-5 text-success shrink-0 mt-0.5" />
      ) : (
        <CircleDashed className={clsx("size-5 shrink-0 mt-0.5 text-faint", pending && "animate-spin")} />
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-[13px] text-muted mt-0.5 leading-relaxed">{done ? doneText : todoText}</div>
      </div>
      {action}
    </div>
  );
}
