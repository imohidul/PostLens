import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { api, type AIStatus, type Dataset, type FacebookState, type UpdateState } from "./api";
import { apply, onSystemChange, resolve, stored, type Accent, type ThemeMode } from "./lib/theme";

type Toast = { id: number; tone: "success" | "error" | "info"; text: string };

interface AppState {
  datasets: Dataset[];
  facebook: FacebookState | null;
  ai: AIStatus | null;
  version: string;
  /** new versions of PostLens (see postlens/updater.py) */
  update: UpdateState | null;
  refreshUpdate: () => Promise<void>;
  setUpdate: (u: UpdateState) => void;
  refreshDatasets: () => Promise<void>;
  refreshFacebook: (deep?: boolean) => Promise<void>;
  refreshAI: () => Promise<void>;
  setFacebook: (f: FacebookState) => void;
  toast: (text: string, tone?: Toast["tone"]) => void;
  /** what the user picked */
  themeMode: ThemeMode;
  /** what is actually shown right now */
  theme: "dark" | "light";
  accent: Accent;
  setThemeMode: (m: ThemeMode) => void;
  setAccent: (a: Accent) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [facebook, setFacebook] = useState<FacebookState | null>(null);
  const [ai, setAI] = useState<AIStatus | null>(null);
  const [version, setVersion] = useState("");
  const [update, setUpdate] = useState<UpdateState | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [themeMode, setThemeModeState] = useState<ThemeMode>(stored().mode);
  const [accent, setAccentState] = useState<Accent>(stored().accent);
  const [theme, setResolved] = useState<"dark" | "light">(resolve(stored().mode));
  const tid = useRef(0);

  const toast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = ++tid.current;
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const refreshDatasets = useCallback(async () => {
    try {
      setDatasets(await api.datasets());
    } catch {
      /* server restarting */
    }
  }, []);
  const refreshFacebook = useCallback(async (deep = false) => {
    try {
      setFacebook(await api.fbStatus(deep));
    } catch {
      /* ignore */
    }
  }, []);
  const refreshAI = useCallback(async () => {
    try {
      setAI(await api.aiStatus());
    } catch {
      /* ignore */
    }
  }, []);

  const refreshUpdate = useCallback(async () => {
    try {
      setUpdate(await api.update());
    } catch {
      /* ignore */
    }
  }, []);

  // Follow update progress: quickly while something is happening, otherwise
  // every few minutes (the app itself checks GitHub every few hours).
  useEffect(() => {
    const busy = update && ["checking", "downloading", "installing"].includes(update.status);
    const t = setTimeout(refreshUpdate, busy ? 1500 : update ? 5 * 60_000 : 8000);
    return () => clearTimeout(t);
  }, [update, refreshUpdate]);

  // Tell the user once when an update has finished downloading.
  const announced = useRef("");
  useEffect(() => {
    if (update?.status === "ready" && update.latest && announced.current !== update.latest) {
      announced.current = update.latest;
      toast(`PostLens ${update.latest} is ready. It installs when you close PostLens, or restart now from the sidebar.`, "success");
    }
  }, [update, toast]);

  // Apply theme; follow the OS when mode is "system".
  useEffect(() => {
    apply(themeMode, accent);
    setResolved(resolve(themeMode));
    if (themeMode !== "system") return;
    return onSystemChange(() => {
      apply("system", accent);
      setResolved(resolve("system"));
    });
  }, [themeMode, accent]);

  const setThemeMode = (m: ThemeMode) => {
    setThemeModeState(m);
    api.saveSettings({ ui: { theme: m } }).catch(() => {});
  };
  const setAccent = (a: Accent) => {
    setAccentState(a);
    api.saveSettings({ ui: { accent: a } }).catch(() => {});
  };

  useEffect(() => {
    api.status().then((s) => {
      setVersion(s.version);
      setFacebook(s.facebook);
    }).catch(() => {});
    // server copy wins, so the choice follows the user across browsers
    api.settings().then((st) => {
      if (st.ui?.theme) setThemeModeState(st.ui.theme);
      if (st.ui?.accent) setAccentState(st.ui.accent);
    }).catch(() => {});
    refreshDatasets();
    refreshAI();
    refreshUpdate();
  }, [refreshDatasets, refreshAI, refreshUpdate]);

  // While a Facebook check or login is in progress, keep polling it.
  useEffect(() => {
    if (!facebook || (!facebook.checking && !facebook.login_running && facebook.logged_in !== null)) return;
    const t = setTimeout(() => refreshFacebook(), 1500);
    return () => clearTimeout(t);
  }, [facebook, refreshFacebook]);

  return (
    <Ctx.Provider
      value={{ datasets, facebook, ai, version, update, refreshUpdate, setUpdate, refreshDatasets, refreshFacebook, refreshAI, setFacebook, toast, themeMode, theme, accent, setThemeMode, setAccent }}
    >
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 w-[360px] max-w-[calc(100vw-2rem)]">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="fade-up flex items-start gap-3 rounded-xl border border-line-strong bg-surface-2/95 backdrop-blur px-4 py-3 shadow-card text-sm"
          >
            {t.tone === "success" ? (
              <CheckCircle2 className="size-4 mt-0.5 text-success shrink-0" />
            ) : t.tone === "error" ? (
              <AlertTriangle className="size-4 mt-0.5 text-danger shrink-0" />
            ) : (
              <Info className="size-4 mt-0.5 text-accent-2 shrink-0" />
            )}
            <span className="flex-1">{t.text}</span>
            <button onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} className="text-faint hover:text-text">
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useApp() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}

export function toneFor(status: string): "success" | "warning" | "danger" | "neutral" | "accent" {
  return status === "done"
    ? "success"
    : status === "running" || status === "pending"
      ? "accent"
      : status === "error"
        ? "danger"
        : status === "cancelled"
          ? "warning"
          : "neutral";
}
