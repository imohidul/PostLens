export const nf = new Intl.NumberFormat();
export const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export function fmtNum(n: number | null | undefined, short = false): string {
  if (n === null || n === undefined) return "—";
  return short && n >= 10000 ? compact.format(n) : nf.format(n);
}

export function fmtDate(ts: number | null | undefined, withTime = false): string {
  if (!ts) return "Unknown date";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

export function timeAgo(ts: number | null | undefined): string {
  if (!ts) return "";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return fmtDate(ts);
}

export function hostPath(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname.replace(/\/$/, "") || u.hostname;
  } catch {
    return url;
  }
}

export const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "3 months" },
  { days: 182, label: "6 months" },
];
