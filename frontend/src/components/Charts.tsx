import { useMemo, useState } from "react";
import clsx from "clsx";

type Day = { date: string; posts: number; comments: number };

function fillDays(data: Day[]): Day[] {
  if (data.length === 0) return [];
  const map = new Map(data.map((d) => [d.date, d]));
  const out: Day[] = [];
  const start = new Date(data[0].date + "T00:00:00Z");
  const end = new Date(data[data.length - 1].date + "T00:00:00Z");
  for (let t = start.getTime(); t <= end.getTime(); t += 86400000) {
    const k = new Date(t).toISOString().slice(0, 10);
    out.push(map.get(k) || { date: k, posts: 0, comments: 0 });
  }
  return out;
}

const fmt = (d: string) => new Date(d + "T00:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

/** Comments per day as bars, with a dot on days a post was published. */
export function ActivityChart({ data }: { data: Day[] }) {
  const days = useMemo(() => fillDays(data), [data]);
  const [hover, setHover] = useState<number | null>(null);
  if (days.length === 0) return <div className="h-48 grid place-items-center text-sm text-faint">No dated activity</div>;

  const max = Math.max(1, ...days.map((d) => d.comments));
  const H = 180;
  const ticks = [0, Math.round(max / 2), max];
  const labelEvery = Math.max(1, Math.ceil(days.length / 7));
  const h = hover !== null ? days[hover] : null;

  return (
    <div className="relative select-none">
      <div className="flex gap-3">
        <div className="flex flex-col justify-between text-[11px] text-faint tabular-nums text-right w-7" style={{ height: H }}>
          {[...ticks].reverse().map((t, i) => (
            <span key={i} className="-translate-y-1.5">{t}</span>
          ))}
        </div>
        <div className="relative flex-1" style={{ height: H }} onMouseLeave={() => setHover(null)}>
          {ticks.map((_, i) => (
            <div key={i} className="absolute inset-x-0 border-t border-dashed border-line" style={{ top: (i * H) / 2 }} />
          ))}
          <div className="absolute inset-0 flex items-end gap-[3px]">
            {days.map((d, i) => (
              <div key={d.date} className="relative flex-1 h-full flex items-end" onMouseEnter={() => setHover(i)}>
                <div
                  className={clsx(
                    "w-full rounded-t-[4px] transition-colors",
                    hover === i ? "bg-accent-2" : "bg-accent/75",
                    d.comments === 0 && "bg-transparent",
                  )}
                  style={{ height: `${Math.max(d.comments ? 3 : 0, (d.comments / max) * 100)}%` }}
                />
                {d.posts > 0 && (
                  <span className="absolute left-1/2 -translate-x-1/2 -bottom-[13px] size-[7px] rounded-full bg-warning ring-2 ring-surface" />
                )}
              </div>
            ))}
          </div>
          {h && (
            <div
              className="absolute z-10 -top-2 -translate-y-full pointer-events-none rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-[12px] shadow-card whitespace-nowrap"
              style={{ left: `${((hover! + 0.5) / days.length) * 100}%`, transform: "translate(-50%, -100%)" }}
            >
              <div className="font-medium">{fmt(h.date)}</div>
              <div className="text-muted mt-0.5">
                <span className="inline-block size-2 rounded-sm bg-accent mr-1.5" />
                {h.comments} comments
              </div>
              {h.posts > 0 && (
                <div className="text-muted">
                  <span className="inline-block size-2 rounded-full bg-warning mr-1.5" />
                  {h.posts} post{h.posts > 1 ? "s" : ""}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="flex gap-3 mt-5">
        <div className="w-7" />
        <div className="flex-1 flex gap-[3px] text-[11px] text-faint">
          {days.map((d, i) => (
            <div key={d.date} className="flex-1 text-center overflow-visible whitespace-nowrap">
              {i % labelEvery === 0 ? fmt(d.date) : ""}
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4 mt-3 text-[12px] text-muted">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-accent" /> Comments per day</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-warning" /> Post published</span>
      </div>
    </div>
  );
}

/** 24 cells showing when comments are written (local time). */
export function HourStrip({ hours }: { hours: number[] }) {
  const max = Math.max(1, ...hours);
  const peak = hours.indexOf(Math.max(...hours));
  const label = (h: number) => (h === 0 ? "12a" : h < 12 ? `${h}a` : h === 12 ? "12p" : `${h - 12}p`);
  return (
    <div>
      <div className="grid grid-cols-24 gap-1" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
        {hours.map((v, i) => (
          <div
            key={i}
            title={`${label(i)} · ${v} comments`}
            className="h-9 rounded-md border border-line"
            style={{ background: `color-mix(in oklab, var(--accent) ${Math.round((v / max) * 85)}%, var(--surface-2))` }}
          />
        ))}
      </div>
      <div className="grid mt-1.5 text-[10.5px] text-faint" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
        {hours.map((_, i) => (
          <div key={i} className="text-center">{i % 3 === 0 ? label(i) : ""}</div>
        ))}
      </div>
      {hours.some((h) => h > 0) && (
        <p className="text-[13px] text-muted mt-3">
          Busiest hour: <span className="text-text font-medium">{label(peak)}–{label((peak + 1) % 24)}</span>
        </p>
      )}
    </div>
  );
}

export function KeywordCloud({ words, onPick }: { words: { word: string; count: number }[]; onPick?: (w: string) => void }) {
  if (!words.length) return <p className="text-sm text-faint">Not enough text yet.</p>;
  const max = words[0].count;
  return (
    <div className="flex flex-wrap gap-1.5">
      {words.map((w) => {
        const r = w.count / max;
        return (
          <button
            key={w.word}
            onClick={() => onPick?.(w.word)}
            className="h-7 px-2.5 rounded-md border text-[13px] transition hover:border-accent/50 hover:text-text"
            style={{
              background: `color-mix(in oklab, var(--accent) ${Math.round(r * 22)}%, var(--surface-2))`,
              borderColor: `color-mix(in oklab, var(--accent) ${Math.round(r * 35)}%, var(--line))`,
              color: r > 0.5 ? "var(--text)" : "var(--muted)",
            }}
          >
            {w.word}
            <span className="ml-1.5 text-[11px] text-faint tabular-nums">{w.count}</span>
          </button>
        );
      })}
    </div>
  );
}
