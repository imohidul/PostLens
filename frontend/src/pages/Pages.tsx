import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink, FileText, Search, X } from "lucide-react";
import { api, type PageRow } from "../api";
import { Badge, Card, Empty, Skeleton } from "../components/ui";
import { fmtNum } from "../lib/format";

export default function Pages({ dsId, initialQuery = "", openId }: { dsId: number; initialQuery?: string; openId?: number }) {
  const [pages, setPages] = useState<PageRow[] | null>(null);
  const [q, setQ] = useState(initialQuery);
  const [sel, setSel] = useState<number | null>(openId ?? null);

  useEffect(() => setQ(initialQuery), [initialQuery]);
  useEffect(() => { if (openId) setSel(openId); }, [openId]);
  useEffect(() => {
    setPages(null);
    api.pages(dsId).then((p) => {
      setPages(p);
      setSel((s) => s ?? p[0]?.id ?? null);
    }).catch(() => setPages([]));
  }, [dsId]);

  const numbered = useMemo(() => (pages || []).map((p, i) => ({ ...p, no: i + 1 })), [pages]);
  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? numbered.filter((p) => (p.title + " " + p.url + " " + p.text).toLowerCase().includes(n)) : numbered;
  }, [numbered, q]);
  const current = numbered.find((p) => p.id === sel);

  if (!pages) return <Skeleton className="h-[560px]" />;
  if (pages.length === 0) return <Card><Empty icon={<FileText className="size-5" />} title="No pages yet" /></Card>;

  return (
    <div className="fade-up grid grid-cols-[320px_1fr] gap-4 h-[calc(100vh-190px)] min-h-[520px]">
      <div className="flex flex-col min-h-0">
        <div className="relative">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search pages…"
            className="h-10 w-full rounded-lg bg-surface border border-line-strong pl-9 pr-9 text-sm placeholder:text-faint focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent-soft transition"
          />
          {q && <button onClick={() => setQ("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-faint hover:text-text"><X className="size-4" /></button>}
        </div>
        <div className="mt-3 text-[12px] text-faint px-1">{shown.length} of {pages.length} pages</div>
        <div className="mt-1.5 flex-1 overflow-y-auto space-y-0.5 pr-1">
          {shown.map((p) => (
            <button
              key={p.id}
              onClick={() => setSel(p.id)}
              className={clsx("w-full text-left rounded-lg px-3 py-2.5 transition", sel === p.id ? "bg-surface-2 shadow-card" : "hover:bg-surface-2/60")}
            >
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-faint tabular-nums">#{p.no}</span>
                <span className="text-[13px] font-medium truncate">{p.title || "Untitled"}</span>
              </div>
              <div className="text-[11.5px] text-faint truncate mt-0.5">
                {(p.status ?? 200) >= 400 ? <span className="text-danger">Error {p.status}</span> : `${fmtNum(p.word_count)} words`} · {new URL(p.url).pathname}
              </div>
            </button>
          ))}
        </div>
      </div>

      <Card className="flex flex-col min-h-0 overflow-hidden">
        {current ? (
          <>
            <div className="px-6 py-4 border-b border-line">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-semibold truncate">{current.title || "Untitled"}</div>
                  <a href={current.url} target="_blank" rel="noreferrer" className="text-[12.5px] text-muted hover:text-text inline-flex items-center gap-1 truncate max-w-full">
                    {current.url} <ExternalLink className="size-3 shrink-0" />
                  </a>
                </div>
                <Badge tone={(current.status ?? 200) >= 400 ? "danger" : "success"} dot>{current.status ?? "OK"}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-faint">
                <span>{fmtNum(current.word_count)} words</span>
                <span>{current.meta.h1_count ?? 0} H1</span>
                <span>{current.meta.links_internal ?? 0} internal links</span>
                <span>{current.meta.links_external ?? 0} external links</span>
                <span>{current.meta.images ?? 0} images{current.meta.images_no_alt ? ` (${current.meta.images_no_alt} without alt)` : ""}</span>
                {current.meta.elapsed_ms != null && <span>{(current.meta.elapsed_ms / 1000).toFixed(2)}s response</span>}
                {!!current.rendered && <span>Rendered with JavaScript</span>}
              </div>
              {current.description && <p className="mt-3 text-[13px] text-muted leading-relaxed"><span className="text-faint">Meta description: </span>{current.description}</p>}
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {current.text ? (
                <div className="prose-pl max-w-3xl"><ReactMarkdown remarkPlugins={[remarkGfm]}>{current.text}</ReactMarkdown></div>
              ) : (
                <p className="text-sm text-muted">No readable main content on this page.</p>
              )}
            </div>
          </>
        ) : (
          <Empty icon={<FileText className="size-5" />} title="Select a page" />
        )}
      </Card>
    </div>
  );
}
