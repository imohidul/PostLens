import { useEffect, useState } from "react";
import { Activity, Clock, Flame, Hash, Heart, MessageCircle, FileText, Sparkles, TrendingUp } from "lucide-react";
import { api, type BriefPost, type Overview as OV } from "../api";
import { Card, CardHeader, Skeleton, Segmented } from "../components/ui";
import { ActivityChart, HourStrip, KeywordCloud } from "../components/Charts";
import { fmtDate, fmtNum } from "../lib/format";

export default function Overview({
  dsId,
  onAsk,
  onSearch,
}: {
  dsId: number;
  onAsk: (q: string) => void;
  onSearch: (w: string) => void;
}) {
  const [ov, setOv] = useState<OV | null>(null);
  const [kwTab, setKwTab] = useState<"comments" | "posts">("comments");
  const [topTab, setTopTab] = useState<"discussed" | "reacted">("discussed");

  useEffect(() => {
    setOv(null);
    api.overview(dsId).then(setOv).catch(() => {});
  }, [dsId]);

  if (!ov)
    return (
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
        <Skeleton className="h-72 col-span-3" />
        <Skeleton className="h-72" />
      </div>
    );

  const t = ov.totals;
  const top = topTab === "discussed" ? ov.most_discussed : ov.most_reacted;

  return (
    <div className="space-y-4 fade-up">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={<FileText className="size-4" />} label="Posts" value={fmtNum(t.posts)} sub={ov.range.first ? `${fmtDate(ov.range.first)} – ${fmtDate(ov.range.last)}` : "Dates unknown"} />
        <Stat icon={<MessageCircle className="size-4" />} label="Comments" value={fmtNum(t.comments)} sub={`${fmtNum(t.replies)} replies · avg ${t.avg_comment_length} chars`} />
        <Stat icon={<TrendingUp className="size-4" />} label="Comments per post" value={String(t.avg_comments_per_post)} sub="Average collected" />
        <Stat icon={<Heart className="size-4" />} label="Reactions" value={fmtNum(t.reactions, true)} sub="Sum across posts" />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader icon={<Activity className="size-4" />} title="Activity" subtitle="When people commented, and when posts went out" />
          <div className="px-5 pb-5 pt-6">
            <ActivityChart data={ov.timeline} />
          </div>
        </Card>
        <Card>
          <CardHeader
            icon={<Hash className="size-4" />}
            title="Recurring words"
            subtitle="Click to find it"
            action={
              <Segmented
                value={kwTab}
                onChange={setKwTab}
                options={[
                  { value: "comments", label: "Comments" },
                  { value: "posts", label: "Posts" },
                ]}
              />
            }
          />
          <div className="px-5 pb-5">
            <KeywordCloud words={(kwTab === "comments" ? ov.comment_keywords : ov.post_keywords).slice(0, 24)} onPick={onSearch} />
          </div>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader
            icon={<Flame className="size-4" />}
            title="Top posts"
            action={
              <Segmented
                value={topTab}
                onChange={setTopTab}
                options={[
                  { value: "discussed", label: "Most discussed" },
                  { value: "reacted", label: "Most reactions" },
                ]}
              />
            }
          />
          <div className="px-2 pb-2">
            {top.length === 0 && <p className="px-3 pb-4 text-sm text-faint">No data for this view.</p>}
            {top.map((p, i) => (
              <TopPost key={p.id} p={p} rank={i + 1} onAsk={onAsk} />
            ))}
          </div>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader icon={<Clock className="size-4" />} title="When people comment" subtitle="Hour of day, your local time" />
            <div className="px-5 pb-5">
              <HourStrip hours={ov.hours} />
            </div>
          </Card>
          <Card className="overflow-hidden">
            <div className="p-5 bg-[radial-gradient(400px_140px_at_0%_0%,var(--accent-soft),transparent)]">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="size-4 text-accent-2" /> Quick AI reads
              </div>
              <div className="mt-3 flex flex-col gap-1.5">
                {[
                  "Summarize what this page posts about and how people react.",
                  "What is the overall sentiment in the comments? Give an estimated split.",
                  "List the most common complaints or problems people mention.",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => onAsk(q)}
                    className="text-left text-[13px] text-muted hover:text-text rounded-lg px-3 py-2 border border-line bg-surface/60 hover:border-accent/40 transition"
                  >
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

function Stat({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-[13px] text-muted">
        <span className="size-7 rounded-lg bg-surface-2 border border-line grid place-items-center text-faint">{icon}</span>
        {label}
      </div>
      <div className="mt-3 text-[28px] font-semibold tracking-[-0.03em] tabular-nums">{value}</div>
      <div className="mt-0.5 text-[12px] text-faint truncate">{sub}</div>
    </Card>
  );
}

function TopPost({ p, rank, onAsk }: { p: BriefPost; rank: number; onAsk: (q: string) => void }) {
  return (
    <div className="group flex gap-3 rounded-xl px-3 py-3 hover:bg-surface-2/70 transition">
      <span className="w-5 text-[13px] text-faint tabular-nums pt-0.5">{rank}</span>
      <div className="flex-1 min-w-0">
        <p className="text-[13.5px] leading-relaxed line-clamp-2">{p.text}</p>
        <div className="mt-1.5 flex items-center gap-3 text-[12px] text-faint">
          <span>{fmtDate(p.created_at)}</span>
          <span className="flex items-center gap-1"><MessageCircle className="size-3" /> {p.comments}</span>
          {p.reactions !== null && <span className="flex items-center gap-1"><Heart className="size-3" /> {fmtNum(p.reactions, true)}</span>}
        </div>
      </div>
      <button
        onClick={() => onAsk(`What are people saying in the comments of the post that starts with: "${p.text.slice(0, 80)}"?`)}
        className="opacity-0 group-hover:opacity-100 self-center h-7 px-2.5 rounded-md text-[12px] text-accent-2 bg-accent-soft transition flex items-center gap-1"
      >
        <Sparkles className="size-3" /> Ask
      </button>
    </div>
  );
}
