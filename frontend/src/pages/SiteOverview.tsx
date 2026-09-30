import { useEffect, useState } from "react";
import clsx from "clsx";
import { AlertCircle, AlertTriangle, ChevronDown, FileText, Gauge, Hash, Info, Languages, Sparkles, Type } from "lucide-react";
import { api, type SiteOverview as SO } from "../api";
import { Card, CardHeader, Skeleton } from "../components/ui";
import { KeywordCloud } from "../components/Charts";
import { fmtNum } from "../lib/format";

export default function SiteOverview({ dsId, onAsk, onSearch, onOpenPage }: {
  dsId: number;
  onAsk: (q: string) => void;
  onSearch: (w: string) => void;
  onOpenPage: (pageId: number) => void;
}) {
  const [ov, setOv] = useState<SO | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    setOv(null);
    api.siteOverview(dsId).then(setOv).catch(() => {});
  }, [dsId]);

  if (!ov)
    return (
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        <Skeleton className="h-72 col-span-3" />
        <Skeleton className="h-72" />
      </div>
    );

  const t = ov.totals;
  const maxWords = Math.max(1, ...ov.pages.map((p) => p.words));
  const byWords = [...ov.pages].sort((a, b) => b.words - a.words).slice(0, 12);

  return (
    <div className="space-y-4 fade-up">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={<FileText className="size-4" />} label="Pages read" value={fmtNum(t.pages)} sub={`${t.ok_pages} readable${t.rendered ? ` · ${t.rendered} needed JavaScript` : ""}`} />
        <Stat icon={<Type className="size-4" />} label="Words of content" value={fmtNum(t.words, true)} sub={`${fmtNum(t.avg_words)} per page on average`} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Issues to fix" value={fmtNum(t.issues)} sub="Errors and warnings below" tone={t.issues ? "warning" : "success"} />
        <Stat icon={<Gauge className="size-4" />} label="Avg. response" value={`${(t.avg_ms / 1000).toFixed(2)}s`} sub="Server response time" />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader icon={<AlertCircle className="size-4" />} title="Content & SEO checks" subtitle="Click a check to see the pages" />
          <div className="px-2 pb-2">
            {ov.issues.length === 0 && <p className="px-3 pb-4 text-sm text-muted">No issues found. Nicely done.</p>}
            {ov.issues.map((i) => (
              <div key={i.title} className="rounded-xl">
                <button
                  onClick={() => setOpen(open === i.title ? null : i.title)}
                  className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-surface-2/70 text-left transition"
                >
                  <SevIcon s={i.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] font-medium">{i.title}</div>
                    <div className="text-[12px] text-muted">{i.detail}</div>
                  </div>
                  <span className="text-[13px] tabular-nums text-muted">{i.count} page{i.count > 1 ? "s" : ""}</span>
                  <ChevronDown className={clsx("size-4 text-faint transition", open === i.title && "rotate-180")} />
                </button>
                {open === i.title && (
                  <div className="pl-11 pr-3 pb-3 space-y-1 fade-up">
                    {i.pages.map((p) => (
                      <button key={p.id} onClick={() => onOpenPage(p.id)} className="block w-full text-left text-[12.5px] text-muted hover:text-text truncate">
                        <span className="text-faint tabular-nums mr-2">#{p.no}</span>{p.title}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader icon={<Hash className="size-4" />} title="Main topics" subtitle="Click to find it" />
          <div className="px-5 pb-5">
            <KeywordCloud words={ov.keywords.slice(0, 24)} onPick={onSearch} />
          </div>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader icon={<FileText className="size-4" />} title="Biggest pages" subtitle="Words of main content per page" />
          <div className="px-5 pb-5 space-y-2">
            {byWords.map((p) => (
              <button key={p.id} onClick={() => onOpenPage(p.id)} className="w-full group text-left">
                <div className="flex items-center justify-between text-[12.5px]">
                  <span className="truncate text-muted group-hover:text-text"><span className="text-faint tabular-nums mr-2">#{p.no}</span>{p.title}</span>
                  <span className="tabular-nums text-faint ml-3">{fmtNum(p.words)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                  <div className="h-full rounded-full bg-accent/80 group-hover:bg-accent transition-all" style={{ width: `${(p.words / maxWords) * 100}%` }} />
                </div>
              </button>
            ))}
          </div>
        </Card>
        <div className="space-y-4">
          {ov.languages.length > 0 && (
            <Card>
              <CardHeader icon={<Languages className="size-4" />} title="Languages" />
              <div className="px-5 pb-5 flex flex-wrap gap-2">
                {ov.languages.map((l) => (
                  <span key={l.lang} className="h-7 px-2.5 rounded-md border border-line bg-surface-2 text-[13px] inline-flex items-center gap-1.5">
                    {l.lang.toUpperCase()} <span className="text-faint text-[11px]">{l.pages}</span>
                  </span>
                ))}
              </div>
            </Card>
          )}
          <Card className="overflow-hidden">
            <div className="p-5 bg-[radial-gradient(400px_140px_at_0%_0%,var(--accent-soft),transparent)]">
              <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-accent-2" /> Quick AI reads</div>
              <div className="mt-3 flex flex-col gap-1.5">
                {[
                  "Summarize what this website offers and who it's for.",
                  "What are the top 5 improvements to this site's content and SEO?",
                  "What questions would a customer still have after reading this site?",
                ].map((q) => (
                  <button key={q} onClick={() => onAsk(q)} className="text-left text-[13px] text-muted hover:text-text rounded-lg px-3 py-2 border border-line bg-surface/60 hover:border-accent/40 transition">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SevIcon({ s }: { s: "error" | "warning" | "info" }) {
  const c = { error: "bg-danger/10 text-danger", warning: "bg-warning/10 text-warning", info: "bg-surface-3 text-muted" }[s];
  const I = s === "info" ? Info : s === "error" ? AlertCircle : AlertTriangle;
  return <span className={clsx("size-8 rounded-lg grid place-items-center shrink-0", c)}><I className="size-4" /></span>;
}

function Stat({ icon, label, value, sub, tone }: { icon: React.ReactNode; label: string; value: string; sub: string; tone?: "warning" | "success" }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-[13px] text-muted">
        <span className="size-7 rounded-lg bg-surface-2 border border-line grid place-items-center text-faint">{icon}</span>
        {label}
      </div>
      <div className={clsx("mt-3 text-[28px] font-semibold tracking-[-0.03em] tabular-nums", tone === "warning" && "text-warning")}>{value}</div>
      <div className="mt-0.5 text-[12px] text-faint truncate">{sub}</div>
    </Card>
  );
}
