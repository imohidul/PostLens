import clsx from "clsx";
import { useState } from "react";
import { ArrowUpCircle, Moon, Plus, Settings, Sun, Sparkles, Database } from "lucide-react";
import { api } from "../api";
import { NavLink, useNavigate } from "react-router-dom";
import { useApp, toneFor } from "../store";
import { LogoMark } from "./Logo";
import { Button, StatusDot } from "./ui";
import { timeAgo, hostPath } from "../lib/format";

export function Sidebar() {
  const { datasets, facebook, ai, theme, setThemeMode, version } = useApp();
  const nav = useNavigate();

  const fbTone = facebook?.logged_in ? "success" : facebook?.checking || facebook?.logged_in === null ? "neutral" : "warning";
  const aiTone = ai?.ok ? "success" : ai ? "warning" : "neutral";

  return (
    <aside className="w-[264px] shrink-0 h-full flex flex-col border-r border-line bg-surface/60 backdrop-blur">
      <div className="h-14 px-4 flex items-center gap-2.5">
        <LogoMark size={26} />
        <span className="font-semibold tracking-[-0.02em] text-[15px]">PostLens</span>
        {version && <span className="ml-auto text-[11px] text-faint tabular-nums">v{version}</span>}
      </div>

      <div className="px-3 pt-1 pb-3">
        <button
          onClick={() => nav("/")}
          className="w-full h-9 rounded-lg flex items-center gap-2 px-3 text-sm font-medium bg-surface-2 border border-line-strong hover:bg-surface-3 transition"
        >
          <Plus className="size-4" /> New analysis
        </button>
      </div>

      <div className="px-4 pt-2 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-faint">Library</div>
      <nav className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {datasets.length === 0 && (
          <div className="mx-2 mt-1 rounded-lg border border-dashed border-line-strong p-3 text-[13px] text-muted">
            <Database className="size-4 mb-1.5 text-faint" />
            Your analyses will appear here.
          </div>
        )}
        {datasets.map((d) => (
          <NavLink
            key={d.id}
            to={`/d/${d.id}`}
            className={({ isActive }) =>
              clsx(
                "group flex items-start gap-2.5 rounded-lg px-2.5 py-2 transition",
                isActive ? "bg-surface-2 shadow-card" : "hover:bg-surface-2/60",
              )
            }
          >
            <span className="mt-1.5">
              <StatusDot tone={toneFor(d.status)} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium">{d.title || hostPath(d.source_url)}</span>
              <span className="block truncate text-[12px] text-faint">
                {d.status === "running" || d.status === "pending"
                  ? "Collecting…"
                  : d.source_type === "website"
                    ? `${d.page_count} pages · ${timeAgo(d.created_at)}`
                    : `${d.post_count} posts · ${d.comment_count} comments · ${timeAgo(d.created_at)}`}
              </span>
            </span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-line p-3 space-y-1">
        <UpdateBanner />
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            clsx("flex items-center gap-2.5 rounded-lg px-2.5 h-9 text-sm transition", isActive ? "bg-surface-2" : "text-muted hover:text-text hover:bg-surface-2/60")
          }
        >
          <Settings className="size-4" /> Settings
        </NavLink>
        <div className="flex items-center gap-2 px-2.5 pt-1.5 text-[12px] text-muted">
          <button onClick={() => nav("/settings#facebook")} className="flex items-center gap-1.5 hover:text-text" title={facebook?.message || ""}>
            <StatusDot tone={fbTone} /> Facebook
          </button>
          <span className="text-faint">·</span>
          <button onClick={() => nav("/settings#ai")} className="flex items-center gap-1.5 hover:text-text" title={ai ? `${ai.provider_name}${ai.model_label ? " · " + ai.model_label : ""} — ${ai.message}` : ""}>
            <StatusDot tone={aiTone} /> <Sparkles className="size-3" /> AI
          </button>
          <button
            onClick={() => setThemeMode(theme === "dark" ? "light" : "dark")}
            title="Switch theme (more options in Settings → Appearance)"
            className="ml-auto size-7 grid place-items-center rounded-md hover:bg-surface-2 hover:text-text"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
          </button>
        </div>
      </div>
    </aside>
  );
}

/** Shows a new version of PostLens: downloading, ready to install, or (when
 * this copy can't update itself) a link to the download page. */
function UpdateBanner() {
  const { update, setUpdate, toast } = useApp();
  const [busy, setBusy] = useState(false);
  if (!update?.available || !update.latest) return null;

  const restart = async () => {
    setBusy(true);
    try {
      setUpdate(await api.updateInstall());
      toast("Restarting into the new version…", "info");
    } catch (e) {
      toast((e as Error).message, "error");
      setBusy(false);
    }
  };
  const download = async () => {
    try {
      setUpdate(await api.updateDownload());
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  let body: React.ReactNode;
  if (update.status === "installing") {
    body = <p className="text-[12px] text-muted mt-1">Installing… PostLens will reopen in a moment.</p>;
  } else if (update.status === "ready" && update.can_install) {
    body = (
      <>
        <p className="text-[12px] text-muted mt-1 leading-relaxed">Installs when you close PostLens.</p>
        <Button size="sm" variant="primary" className="w-full mt-2" loading={busy} onClick={restart}>
          Restart to update
        </Button>
      </>
    );
  } else if (update.status === "downloading") {
    body = (
      <>
        <p className="text-[12px] text-muted mt-1">Downloading… {Math.round(update.progress * 100)}%</p>
        <div className="mt-1.5 h-1 rounded-full bg-surface-3 overflow-hidden">
          <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(update.progress * 100)}%` }} />
        </div>
      </>
    );
  } else if (update.can_install) {
    body = (
      <Button size="sm" className="w-full mt-2" onClick={download}>
        Download update
      </Button>
    );
  } else {
    body = (
      <a href={update.page_url} target="_blank" rel="noreferrer" className="block text-[12px] text-accent-2 hover:underline mt-1">
        Download from GitHub
      </a>
    );
  }

  return (
    <div className="mb-2 rounded-lg border border-line-strong bg-surface-2 p-2.5">
      <div className="flex items-center gap-1.5 text-[13px] font-medium">
        <ArrowUpCircle className="size-4 text-accent-2" />
        {update.status === "ready" ? `Update ${update.latest} ready` : `PostLens ${update.latest} is available`}
      </div>
      {body}
    </div>
  );
}
