import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import { AlertTriangle, ArrowUp, Check, Copy, MessageSquarePlus, RefreshCw, Sparkles, Square, Trash2, Zap } from "lucide-react";
import { api, type Chat as ChatT, type Message } from "../api";
import { useApp } from "../store";
import { Button } from "../components/ui";
import { LogoMark } from "../components/Logo";
import { timeAgo } from "../lib/format";

const WEB_SUGGESTIONS = [
  { t: "What this site offers", q: "Summarize what this website offers, who it's for, and its main value proposition." },
  { t: "Improve SEO", q: "What are the top 5 SEO and content improvements for this site? Be specific and cite pages." },
  { t: "Unanswered questions", q: "What questions would a visitor still have after reading this site?" },
  { t: "Key facts", q: "List the key facts: products or services, prices, locations, contact options and policies mentioned." },
  { t: "Tone & messaging", q: "Describe the tone of voice and messaging. Is it consistent across pages?" },
  { t: "Content gaps", q: "Which important topics are missing or covered too thinly? Suggest new pages." },
];

const SUGGESTIONS = [
  { t: "Summarize the main topics", q: "Summarize the main topics this page posts about and how people respond to each." },
  { t: "Overall sentiment", q: "What is the overall sentiment in the comments? Give an estimated positive / neutral / negative split with examples." },
  { t: "Top complaints", q: "What are the most common complaints or problems people mention? Rank them." },
  { t: "Questions people ask", q: "What questions do commenters ask most often? Group similar ones." },
  { t: "Best performing post", q: "Which post got the most engagement and what might explain it?" },
  { t: "Content ideas", q: "Based on what commenters ask for and react to, suggest 5 post ideas." },
];

type Live = { content: string; meta?: Message["meta"]; error?: string; streaming: boolean };

export default function Chat({ dsId, kind, prefill, onPrefillUsed }: {
  dsId: number;
  kind: "facebook" | "website";
  prefill?: string;
  onPrefillUsed: () => void;
}) {
  const suggestions = kind === "website" ? WEB_SUGGESTIONS : SUGGESTIONS;
  const { ai } = useApp();
  const nav = useNavigate();
  const [chats, setChats] = useState<ChatT[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);

  const loadChats = useCallback(async () => {
    const c = await api.chats(dsId);
    setChats(c);
    return c;
  }, [dsId]);

  useEffect(() => {
    setActive(null);
    setMsgs([]);
    loadChats().then((c) => c[0] && setActive(c[0].id));
    // Local AI: load the model and pre-read this dataset while the user types
    api.warm(dsId).catch(() => {});
  }, [dsId, loadChats]);

  useEffect(() => {
    if (active) api.messages(active).then(setMsgs);
    else setMsgs([]);
  }, [active]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs, live?.content, pending]);

  const send = useCallback(
    async (text: string, regenerate = false) => {
      const q = text.trim();
      if (!q || live?.streaming) return;
      setInput("");
      let chatId = active;
      if (!chatId) {
        chatId = (await api.newChat(dsId)).id;
        setActive(chatId);
      }
      setPending(q);
      setLive({ content: "", streaming: true });
      const ctrl = new AbortController();
      abort.current = ctrl;
      let content = "";
      let meta: Message["meta"] = null;
      let error: string | undefined;
      try {
        await api.ask(
          chatId,
          q,
          (e) => {
            if (e.type === "meta") meta = e;
            if (e.type === "token") {
              content += e.text;
              setLive({ content, meta, streaming: true });
            }
            if (e.type === "error") error = e.message;
          },
          ctrl.signal,
          regenerate,
        );
      } catch (e) {
        if ((e as Error).name !== "AbortError") error = (e as Error).message;
      }
      const fresh = await api.messages(chatId);
      setMsgs(fresh);
      setPending(null);
      setLive(error ? { content: "", error, streaming: false } : null);
      loadChats();
    },
    [active, dsId, live?.streaming, loadChats],
  );

  useEffect(() => {
    if (prefill) {
      onPrefillUsed();
      send(prefill);
    }
  }, [prefill]);

  const newChat = () => {
    setActive(null);
    setMsgs([]);
    setLive(null);
    ta.current?.focus();
  };

  const removeChat = async (id: number) => {
    await api.deleteChat(id);
    const c = await loadChats();
    if (id === active) setActive(c[0]?.id ?? null);
  };

  const empty = msgs.length === 0 && !pending;

  return (
    <div className="fade-up grid grid-cols-[220px_1fr] gap-4 h-[calc(100vh-190px)] min-h-[520px]">
      {/* Chat list */}
      <div className="flex flex-col min-h-0">
        <Button onClick={newChat} icon={<MessageSquarePlus className="size-4" />} className="w-full justify-start">
          New chat
        </Button>
        <div className="mt-3 flex-1 overflow-y-auto space-y-0.5">
          {chats.map((c) => (
            <div
              key={c.id}
              onClick={() => setActive(c.id)}
              className={clsx(
                "group cursor-pointer rounded-lg px-3 py-2 flex items-start gap-2 transition",
                c.id === active ? "bg-surface-2" : "hover:bg-surface-2/60",
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="text-[13px] truncate">{c.title}</div>
                <div className="text-[11.5px] text-faint">{timeAgo(c.created_at)}</div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeChat(c.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-faint hover:text-danger mt-0.5"
                aria-label="Delete chat"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div className="flex flex-col min-h-0 rounded-2xl border border-line bg-surface shadow-card overflow-hidden">
        <div ref={scroller} className="flex-1 overflow-y-auto">
          {empty ? (
            <div className="h-full flex flex-col items-center justify-center px-8 py-10">
              <LogoMark size={40} />
              <h2 className="mt-4 text-lg font-semibold tracking-[-0.02em]">Ask anything about this page</h2>
              <p className="text-sm text-muted mt-1 text-center max-w-md">
                Answers are based only on the collected posts and comments, and point to post numbers so you can check them.
              </p>
              {!ai?.ok && (
                <button
                  onClick={() => nav("/settings#ai")}
                  className="mt-4 flex items-center gap-2 text-[13px] text-warning bg-warning/10 border border-warning/20 rounded-lg px-3 py-2"
                >
                  <AlertTriangle className="size-4" /> {ai ? `${ai.provider_name}: ${ai.message}` : "AI not configured"} · Open settings
                </button>
              )}
              <div className="mt-7 grid grid-cols-2 lg:grid-cols-3 gap-2 w-full max-w-2xl">
                {suggestions.map((s) => (
                  <button
                    key={s.t}
                    onClick={() => send(s.q)}
                    className="text-left rounded-xl border border-line bg-surface-2/50 hover:bg-surface-2 hover:border-accent/40 p-3 transition"
                  >
                    <Sparkles className="size-3.5 text-accent-2" />
                    <div className="mt-2 text-[13px] font-medium">{s.t}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
              {msgs.map((m, i) => (
                <Bubble
                  key={m.id}
                  role={m.role}
                  content={m.content}
                  meta={m.meta}
                  unit={kind === "website" ? "page" : "post"}
                  onRegenerate={m.role === "assistant" && m.meta?.cached && msgs[i - 1]?.role === "user" && !live?.streaming
                    ? () => send(msgs[i - 1].content, true) : undefined}
                />
              ))}
              {pending && <Bubble role="user" content={pending} />}
              {live && (live.streaming || live.error) && (
                <Bubble role="assistant" content={live.content} meta={live.meta} streaming={live.streaming} error={live.error} unit={kind === "website" ? "page" : "post"} />
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="border-t border-line p-3">
          <div className="max-w-3xl mx-auto flex items-end gap-2 rounded-xl border border-line-strong bg-surface-2 px-3 py-2 focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent-soft transition">
            <textarea
              ref={ta}
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(160, e.target.scrollHeight) + "px";
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder={kind === "website" ? "Ask about this website…" : "Ask about the posts and comments…"}
              className="flex-1 resize-none bg-transparent text-sm leading-6 py-1 placeholder:text-faint focus:outline-none max-h-40"
            />
            {live?.streaming ? (
              <button
                onClick={() => abort.current?.abort()}
                className="size-8 rounded-lg bg-surface-3 border border-line-strong grid place-items-center hover:bg-surface"
                aria-label="Stop"
              >
                <Square className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                onClick={() => send(input)}
                disabled={!input.trim()}
                className="size-8 rounded-lg bg-accent text-accent-ink grid place-items-center disabled:opacity-40 transition hover:brightness-110"
                aria-label="Send"
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>
          <div className="max-w-3xl mx-auto mt-1.5 flex justify-between text-[11px] text-faint px-1">
            <span>{ai?.ok ? (ai.provider === "ollama" ? "Local AI · on this computer" : `${ai.provider_name} · ${ai.model_label}`) : ""}</span>
            <span>AI can be wrong. Check important answers against the {kind === "website" ? "pages" : "posts"}.</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({
  role,
  content,
  meta,
  streaming,
  error,
  unit = "post",
  onRegenerate,
}: {
  role: "user" | "assistant";
  content: string;
  meta?: Message["meta"];
  streaming?: boolean;
  error?: string;
  unit?: "post" | "page";
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  if (role === "user")
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-soft border border-accent/15 px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap">
          {content}
        </div>
      </div>
    );

  return (
    <div className="flex gap-3">
      <div className="shrink-0 mt-0.5">
        <LogoMark size={24} />
      </div>
      <div className="min-w-0 flex-1">
        {error ? (
          <div className="flex items-start gap-2 rounded-xl border border-danger/25 bg-danger/10 text-danger px-4 py-3 text-sm">
            <AlertTriangle className="size-4 mt-0.5 shrink-0" /> {error}
          </div>
        ) : !content && streaming ? (
          <div className="flex items-center gap-2 text-sm text-muted py-1">
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span key={i} className="size-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: `${i * 120}ms` }} />
              ))}
            </span>
            {unit === "page" ? "Reading the pages…" : "Reading the comments…"}
          </div>
        ) : (
          <div className={clsx("prose-pl", streaming && "caret")}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
        {!streaming && !error && content && (
          <div className="mt-2 flex items-center gap-3 text-[11.5px] text-faint">
            <button
              onClick={() => {
                navigator.clipboard.writeText(content);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="flex items-center gap-1 hover:text-text"
            >
              {copied ? <Check className="size-3" /> : <Copy className="size-3" />} {copied ? "Copied" : "Copy"}
            </button>
            {meta?.provider_name && <span>{meta.provider_name}</span>}
            {meta?.cached ? (
              <span className="inline-flex items-center gap-1 text-success"><Zap className="size-3" /> Instant · saved answer</span>
            ) : meta?.ttft_ms != null ? (
              <span className="inline-flex items-center gap-1" title={meta.total_ms ? `Complete answer in ${(meta.total_ms / 1000).toFixed(1)}s` : ""}>
                <Zap className="size-3" /> First words in {(meta.ttft_ms / 1000).toFixed(1)}s
              </span>
            ) : null}
            {meta && meta.complete === false && meta.refs_used && (
              <span title={`${unit === "page" ? "Pages" : "Posts"} read: ${meta.refs_used.join(", ")}`}>
                Used {meta.refs_used.length} most relevant {unit}s
              </span>
            )}
            {meta?.complete && <span>Read every {unit}</span>}
            {onRegenerate && (
              <button onClick={onRegenerate} className="inline-flex items-center gap-1 hover:text-text">
                <RefreshCw className="size-3" /> Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
