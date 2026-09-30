import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import clsx from "clsx";
import {
  AlertTriangle, BarChart3, Check, Download, ExternalLink, FileJson, FileSpreadsheet, ListTree, MoreHorizontal,
  RotateCw, Sparkles, Trash2, X, Globe, MousePointer2, MessagesSquare, CheckCircle2,
} from "lucide-react";
import { api, type Dataset as DS, type Job } from "../api";
import { useApp } from "../store";
import { Badge, Button, Card, Skeleton } from "../components/ui";
import Overview from "./Overview";
import Posts from "./Posts";
import Chat from "./Chat";
import SiteOverview from "./SiteOverview";
import Pages from "./Pages";
import { fmtDate, hostPath } from "../lib/format";

type Tab = "overview" | "posts" | "ask";

export default function Dataset() {
  const id = Number(useParams().id);
  const nav = useNavigate();
  const { refreshDatasets, toast } = useApp();
  const [ds, setDs] = useState<DS | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [prefill, setPrefill] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [openPage, setOpenPage] = useState<number | undefined>();
  const [menu, setMenu] = useState(false);

  const load = useCallback(async () => {
    try {
      setDs(await api.dataset(id));
    } catch {
      nav("/");
    }
  }, [id, nav]);

  useEffect(() => {
    setDs(null);
    setTab("overview");
    load();
  }, [load]);

  const running = ds?.status === "running" || ds?.status === "pending";

  const onFinished = useCallback(() => {
    load();
    refreshDatasets();
  }, [load, refreshDatasets]);

  const remove = async () => {
    if (!confirm("Delete this analysis and its chats? This can't be undone.")) return;
    await api.deleteDataset(id);
    await refreshDatasets();
    toast("Analysis deleted", "success");
    nav("/");
  };

  const rerun = async () => {
    if (!ds) return;
    try {
      let opts: { mode?: "page" | "site"; max_pages?: number } = {};
      try {
        opts = JSON.parse((ds as unknown as { options?: string }).options || "{}");
      } catch {
        /* older dataset */
      }
      const { id: nid } = await api.startScrape(
        ds.source_type === "website" ? { url: ds.source_url, mode: opts.mode, max_pages: opts.max_pages } : { url: ds.source_url, range_days: ds.range_days },
      );
      await refreshDatasets();
      nav(`/d/${nid}`);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  if (!ds)
    return (
      <div className="max-w-6xl mx-auto px-8 py-8 space-y-4">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-6 w-60" />
        <Skeleton className="h-96" />
      </div>
    );

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <BarChart3 className="size-4" /> },
    ds.source_type === "website"
      ? { id: "posts", label: "Pages", icon: <ListTree className="size-4" /> }
      : { id: "posts", label: "Posts & comments", icon: <ListTree className="size-4" /> },
    { id: "ask", label: "Ask AI", icon: <Sparkles className="size-4" /> },
  ];

  return (
    <div className="max-w-6xl mx-auto px-8 pt-8 pb-10">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-[26px] font-semibold tracking-[-0.03em] truncate">{ds.title || hostPath(ds.source_url)}</h1>
            <StatusBadge status={ds.status} />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
            <a href={ds.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-text">
              {hostPath(ds.source_url)} <ExternalLink className="size-3" />
            </a>
            {ds.source_type !== "website" && <span>Last {ds.range_days} days</span>}
            <span>Collected {fmtDate(ds.created_at, true)}</span>
            {!running && (ds.source_type === "website"
              ? <span>{ds.page_count} pages · {ds.word_count.toLocaleString()} words</span>
              : <span>{ds.post_count} posts · {ds.comment_count} comments</span>)}
          </div>
        </div>
        {!running && (
          <div className="relative flex items-center gap-2">
            <Button size="sm" icon={<RotateCw className="size-3.5" />} onClick={rerun}>
              Refresh data
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMenu(!menu)} aria-label="More">
              <MoreHorizontal className="size-4" />
            </Button>
            {menu && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
                <div className="absolute right-0 top-10 z-20 w-52 rounded-xl border border-line-strong bg-surface-2 shadow-card p-1 fade-up">
                  <MenuItem href={`/api/datasets/${id}/export?format=csv`} icon={<FileSpreadsheet className="size-4" />}>Export CSV (Excel)</MenuItem>
                  <MenuItem href={`/api/datasets/${id}/export?format=json`} icon={<FileJson className="size-4" />}>Export JSON</MenuItem>
                  <div className="my-1 border-t border-line" />
                  <button onClick={remove} className="w-full flex items-center gap-2.5 px-3 h-9 rounded-lg text-sm text-danger hover:bg-danger/10">
                    <Trash2 className="size-4" /> Delete analysis
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {running ? (
        <Progress id={id} onFinished={onFinished} website={ds.source_type === "website"} />
      ) : ds.status === "error" && ds.post_count === 0 ? (
        <ErrorState ds={ds} onRetry={rerun} />
      ) : (
        <>
          {ds.status !== "done" && (
            <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-warning/25 bg-warning/10 px-4 py-3 text-[13px] text-warning">
              <AlertTriangle className="size-4 mt-0.5 shrink-0" />
              {ds.status === "cancelled" ? "This run was stopped early. Showing the data collected so far." : ds.error}
            </div>
          )}
          <div className="mt-6 mb-5 flex items-center gap-1 border-b border-line">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "relative flex items-center gap-2 h-10 px-3 text-sm font-medium transition",
                  tab === t.id ? "text-text" : "text-muted hover:text-text",
                )}
              >
                {t.icon}
                {t.label}
                {tab === t.id && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />}
              </button>
            ))}
          </div>
          {tab === "overview" && ds.source_type === "website" && (
            <SiteOverview
              dsId={id}
              onAsk={(q) => { setPrefill(q); setTab("ask"); }}
              onSearch={(w) => { setSearch(w); setOpenPage(undefined); setTab("posts"); }}
              onOpenPage={(pid) => { setSearch(""); setOpenPage(pid); setTab("posts"); }}
            />
          )}
          {tab === "overview" && ds.source_type !== "website" && (
            <Overview
              dsId={id}
              onAsk={(q) => {
                setPrefill(q);
                setTab("ask");
              }}
              onSearch={(w) => {
                setSearch(w);
                setTab("posts");
              }}
            />
          )}
          {tab === "posts" && (ds.source_type === "website"
            ? <Pages dsId={id} initialQuery={search} openId={openPage} />
            : <Posts dsId={id} initialQuery={search} />)}
          {tab === "ask" && <Chat dsId={id} kind={ds.source_type} prefill={prefill} onPrefillUsed={() => setPrefill(undefined)} />}
        </>
      )}
    </div>
  );
}

function MenuItem({ href, icon, children }: { href: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <a href={href} className="flex items-center gap-2.5 px-3 h-9 rounded-lg text-sm hover:bg-surface-3">
      {icon} {children} <Download className="size-3.5 ml-auto text-faint" />
    </a>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "done") return <Badge tone="success" dot>Ready</Badge>;
  if (status === "running" || status === "pending") return <Badge tone="accent" dot>Collecting</Badge>;
  if (status === "cancelled") return <Badge tone="warning" dot>Partial</Badge>;
  return <Badge tone="danger" dot>Failed</Badge>;
}

const FB_STAGES = [
  { key: ["starting"], label: "Open browser", icon: Globe },
  { key: ["feed"], label: "Scroll the page", icon: MousePointer2 },
  { key: ["comments"], label: "Read comments", icon: MessagesSquare },
  { key: ["indexing"], label: "Prepare AI", icon: Sparkles },
  { key: ["done"], label: "Done", icon: CheckCircle2 },
];
const WEB_STAGES = [
  { key: ["starting"], label: "Check the site", icon: Globe },
  { key: ["discover"], label: "Find pages", icon: MousePointer2 },
  { key: ["pages"], label: "Read pages", icon: ListTree },
  { key: ["indexing"], label: "Prepare AI", icon: Sparkles },
  { key: ["done"], label: "Done", icon: CheckCircle2 },
];

function Progress({ id, onFinished, website }: { id: number; onFinished: () => void; website: boolean }) {
  const STAGES = website ? WEB_STAGES : FB_STAGES;
  const [job, setJob] = useState<Job | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const j = await api.job(id);
        if (!alive) return;
        setJob(j);
        if (!["running", "pending"].includes(j.status)) return onFinished();
      } catch {
        /* retry */
      }
      if (alive) setTimeout(tick, 1200);
    };
    tick();
    return () => {
      alive = false;
    };
  }, [id, onFinished]);

  const stageIdx = Math.max(0, STAGES.findIndex((s) => s.key.includes(job?.stage || "")));
  const pct = !job ? null
    : website && job.stage === "pages" && job.pages_found ? Math.round(((job.pages_done ?? 0) / job.pages_found) * 100)
    : !website && job.stage === "comments" && job.posts_found ? Math.round((job.posts_done / job.posts_found) * 100)
    : null;
  const elapsed = job ? Math.max(0, Math.floor(Date.now() / 1000 - job.started_at)) : 0;

  return (
    <Card className="mt-8 overflow-hidden">
      <div className="p-8 bg-[radial-gradient(600px_200px_at_50%_0%,var(--accent-soft),transparent)]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold tracking-[-0.02em]">{website ? "Reading the website" : "Collecting posts and comments"}</div>
            <div className="text-sm text-muted mt-1">{job?.message || "Starting…"}</div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            loading={stopping}
            icon={<X className="size-3.5" />}
            onClick={async () => {
              setStopping(true);
              await api.cancelJob(id);
            }}
          >
            Stop & keep data
          </Button>
        </div>

        <div className="mt-8 grid grid-cols-5 gap-3">
          {STAGES.map((s, i) => {
            const Icon = s.icon;
            const state = i < stageIdx ? "done" : i === stageIdx ? "active" : "todo";
            return (
              <div
                key={s.label}
                className={clsx(
                  "rounded-xl border p-3.5 transition",
                  state === "active" ? "border-accent/40 bg-accent-soft" : "border-line bg-surface/60",
                  state === "todo" && "opacity-60",
                )}
              >
                <div className={clsx("size-7 rounded-lg grid place-items-center", state === "done" ? "bg-success/15 text-success" : state === "active" ? "bg-accent text-accent-ink" : "bg-surface-2 text-faint")}>
                  {state === "done" ? <Check className="size-4" /> : <Icon className="size-4" />}
                </div>
                <div className="mt-2.5 text-[13px] font-medium">{s.label}</div>
              </div>
            );
          })}
        </div>

        <div className="mt-6 h-1.5 rounded-full bg-surface-3 overflow-hidden">
          {pct === null ? (
            <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-transparent via-accent to-transparent bar-indeterminate" />
          ) : (
            <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${pct}%` }} />
          )}
        </div>

        <div className="mt-6 grid grid-cols-3 gap-3">
          {website ? (
            <>
              <Counter label="Pages found" value={job?.pages_found ?? 0} />
              <Counter label="Pages read" value={job?.pages_done ?? 0} />
              <Counter label="Words" value={job?.words ?? 0} />
            </>
          ) : (
            <>
              <Counter label="Posts found" value={job?.posts_found ?? 0} />
              <Counter label="Posts read" value={job?.posts_done ?? 0} />
              <Counter label="Comments" value={job?.comments ?? 0} />
            </>
          )}
        </div>
      </div>
      <div className="border-t border-line px-8 py-4 text-[13px] text-muted flex items-center justify-between">
        <span>{website ? "PostLens reads pages politely, following the site's robots.txt rules." : "A browser window may open. Leave it alone while PostLens works."}</span>
        <span className="tabular-nums text-faint">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} elapsed</span>
      </div>
    </Card>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface/70 px-4 py-3">
      <div className="text-[12px] text-faint">{label}</div>
      <div className="text-2xl font-semibold tabular-nums tracking-[-0.02em] mt-0.5">{value}</div>
    </div>
  );
}

function ErrorState({ ds, onRetry }: { ds: DS; onRetry: () => void }) {
  const nav = useNavigate();
  const login = /log in|connect/i.test(ds.error || "");
  return (
    <Card className="mt-8 p-10 text-center">
      <div className="mx-auto size-12 rounded-2xl bg-danger/10 border border-danger/20 text-danger grid place-items-center">
        <AlertTriangle className="size-5" />
      </div>
      <h2 className="mt-4 font-semibold text-lg">Couldn't collect this page</h2>
      <p className="mt-1.5 text-sm text-muted max-w-lg mx-auto">{ds.error}</p>
      <div className="mt-6 flex justify-center gap-2">
        {login && <Button variant="primary" onClick={() => nav("/settings#facebook")}>Connect Facebook</Button>}
        <Button onClick={onRetry} icon={<RotateCw className="size-4" />}>Try again</Button>
      </div>
    </Card>
  );
}
