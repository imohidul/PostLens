import { useEffect, useMemo, useState } from "react";
import { ChevronDown, CornerDownRight, Heart, MessageCircle, Search, Share2, X } from "lucide-react";
import clsx from "clsx";
import { api, type Post } from "../api";
import { Card, Empty, Segmented, Skeleton } from "../components/ui";
import { fmtDate, fmtNum } from "../lib/format";

type Sort = "newest" | "comments" | "reactions";

function Highlight({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const parts = text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return (
    <>
      {parts.map((p, i) =>
        p.toLowerCase() === q.toLowerCase() ? (
          <mark key={i} className="bg-accent-soft text-text rounded px-0.5">{p}</mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export default function Posts({ dsId, initialQuery = "" }: { dsId: number; initialQuery?: string }) {
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [q, setQ] = useState(initialQuery);
  const [sort, setSort] = useState<Sort>("newest");

  useEffect(() => setQ(initialQuery), [initialQuery]);
  useEffect(() => {
    setPosts(null);
    api.posts(dsId).then(setPosts).catch(() => setPosts([]));
  }, [dsId]);

  const numbered = useMemo(() => (posts || []).map((p, i) => ({ ...p, no: i + 1 })), [posts]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let list = numbered;
    if (needle) {
      list = list
        .map((p) => ({
          ...p,
          comments: p.text.toLowerCase().includes(needle) ? p.comments : p.comments.filter((c) => c.text.toLowerCase().includes(needle)),
        }))
        .filter((p) => p.text.toLowerCase().includes(needle) || p.comments.length > 0);
    }
    const s = [...list];
    if (sort === "comments") s.sort((a, b) => b.comments.length - a.comments.length);
    if (sort === "reactions") s.sort((a, b) => (b.reactions || 0) - (a.reactions || 0));
    return s;
  }, [numbered, q, sort]);

  const matchCount = q.trim() ? shown.reduce((n, p) => n + p.comments.length, 0) : null;

  return (
    <div className="fade-up">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search posts and comments…"
            className="h-10 w-full rounded-lg bg-surface border border-line-strong pl-9 pr-9 text-sm placeholder:text-faint focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent-soft transition"
          />
          {q && (
            <button onClick={() => setQ("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-faint hover:text-text">
              <X className="size-4" />
            </button>
          )}
        </div>
        <Segmented
          value={sort}
          onChange={setSort}
          options={[
            { value: "newest", label: "Newest" },
            { value: "comments", label: "Most comments" },
            { value: "reactions", label: "Most reactions" },
          ]}
        />
      </div>
      {matchCount !== null && (
        <p className="text-[13px] text-muted mb-3">
          {shown.length} posts · {matchCount} matching comments
        </p>
      )}

      {!posts ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : shown.length === 0 ? (
        <Card><Empty icon={<Search className="size-5" />} title="Nothing matches" text="Try a different word." /></Card>
      ) : (
        <div className="space-y-3">
          {shown.map((p) => <PostCard key={p.id} post={p} q={q.trim()} forceOpen={!!q.trim()} />)}
        </div>
      )}
    </div>
  );
}

function PostCard({ post, q, forceOpen }: { post: Post & { no: number }; q: string; forceOpen: boolean }) {
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const isOpen = open || forceOpen;
  const visible = all ? post.comments : post.comments.slice(0, 8);

  return (
    <Card className="overflow-hidden">
      <div className="p-5">
        <div className="flex items-center gap-2 text-[12px] text-faint mb-2">
          <span className="h-5 px-1.5 rounded bg-surface-2 border border-line text-muted font-medium tabular-nums">#{post.no}</span>
          <span>{fmtDate(post.created_at, true)}</span>
        </div>
        <p className="text-[14.5px] leading-relaxed whitespace-pre-line"><Highlight text={post.text} q={q} /></p>
        <div className="mt-4 flex items-center gap-5 text-[13px] text-muted">
          {post.reactions !== null && <span className="flex items-center gap-1.5"><Heart className="size-3.5" /> {fmtNum(post.reactions)}</span>}
          {post.shares !== null && <span className="flex items-center gap-1.5"><Share2 className="size-3.5" /> {fmtNum(post.shares)}</span>}
          <button
            onClick={() => setOpen(!open)}
            disabled={post.comments.length === 0}
            className="flex items-center gap-1.5 hover:text-text disabled:opacity-60 disabled:hover:text-muted"
          >
            <MessageCircle className="size-3.5" />
            {post.comments.length} collected
            {post.comment_total !== null && post.comment_total > post.comments.length && (
              <span className="text-faint">of {fmtNum(post.comment_total)}</span>
            )}
            {post.comments.length > 0 && <ChevronDown className={clsx("size-3.5 transition", isOpen && "rotate-180")} />}
          </button>
        </div>
      </div>
      {isOpen && post.comments.length > 0 && (
        <div className="border-t border-line bg-surface-2/40 px-5 py-3 space-y-1">
          {visible.map((c) => (
            <div key={c.id} className={clsx("flex gap-3 py-2", c.is_reply && "pl-7")}>
              {c.is_reply ? (
                <CornerDownRight className="size-3.5 text-faint mt-1 shrink-0" />
              ) : (
                <span className="size-6 rounded-full bg-surface-3 border border-line shrink-0 grid place-items-center text-[10px] text-faint">?</span>
              )}
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] leading-relaxed whitespace-pre-line"><Highlight text={c.text} q={q} /></p>
                <div className="mt-1 text-[11.5px] text-faint flex gap-3">
                  <span>Anonymous</span>
                  {c.created_at && <span>{fmtDate(c.created_at, true)}</span>}
                  {!!c.reactions && <span className="flex items-center gap-1"><Heart className="size-3" /> {c.reactions}</span>}
                </div>
              </div>
            </div>
          ))}
          {post.comments.length > 8 && (
            <button onClick={() => setAll(!all)} className="text-[13px] text-accent-2 hover:underline py-2">
              {all ? "Show fewer" : `Show all ${post.comments.length} comments`}
            </button>
          )}
        </div>
      )}
    </Card>
  );
}
