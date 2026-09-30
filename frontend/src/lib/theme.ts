export type ThemeMode = "system" | "light" | "dark";
export type Accent = "violet" | "blue" | "emerald" | "rose" | "amber" | "graphite";

export const ACCENTS: { id: Accent; label: string; dark: string; light: string }[] = [
  { id: "violet", label: "Violet", dark: "#7c6cff", light: "#5b4cf0" },
  { id: "blue", label: "Ocean", dark: "#3b82f6", light: "#2563eb" },
  { id: "emerald", label: "Emerald", dark: "#10b981", light: "#047857" },
  { id: "rose", label: "Rose", dark: "#f43f5e", light: "#e11d48" },
  { id: "amber", label: "Amber", dark: "#f59e0b", light: "#b45309" },
  { id: "graphite", label: "Graphite", dark: "#e4e4e7", light: "#18181b" },
];

const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function resolve(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? (media().matches ? "dark" : "light") : mode;
}

/** Apply to <html>. Also remembered locally so the first paint is correct
 *  before the server settings load (see the inline script in index.html). */
export function apply(mode: ThemeMode, accent: Accent) {
  const root = document.documentElement;
  root.dataset.theme = resolve(mode);
  root.dataset.accent = accent;
  try {
    localStorage.setItem("pl-theme", mode);
    localStorage.setItem("pl-accent", accent);
  } catch {
    /* storage blocked - harmless */
  }
}

export function stored(): { mode: ThemeMode; accent: Accent } {
  try {
    return {
      mode: (localStorage.getItem("pl-theme") as ThemeMode) || "system",
      accent: (localStorage.getItem("pl-accent") as Accent) || "violet",
    };
  } catch {
    return { mode: "system", accent: "violet" };
  }
}

export function onSystemChange(cb: () => void): () => void {
  const m = media();
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}
