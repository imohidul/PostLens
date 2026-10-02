import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap select-none",
        "transition-[background,color,box-shadow,transform,opacity] duration-150 active:scale-[0.98]",
        "disabled:opacity-50 disabled:pointer-events-none",
        {
          sm: "h-8 px-3 text-[13px]",
          md: "h-9 px-3.5 text-sm",
          lg: "h-11 px-5 text-[15px]",
        }[size],
        {
          primary:
            "bg-accent text-accent-ink shadow-[0_0_0_1px_rgba(255,255,255,0.08)_inset,0_6px_20px_-6px_var(--accent)] hover:brightness-110",
          secondary: "bg-surface-2 text-text border border-line-strong hover:bg-surface-3",
          ghost: "text-muted hover:text-text hover:bg-surface-2",
          danger: "bg-danger/10 text-danger border border-danger/25 hover:bg-danger/15",
        }[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={clsx("rounded-2xl border border-line bg-surface shadow-card", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action, icon }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-5 pb-3">
      <div className="flex items-center gap-2.5 min-w-0">
        {icon && <span className="text-faint">{icon}</span>}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-[-0.01em] whitespace-nowrap">{title}</h3>
          {subtitle && <p className="text-[13px] text-muted mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function Badge({ tone = "neutral", children, dot, className }: { tone?: "neutral" | "accent" | "success" | "warning" | "danger"; children: ReactNode; dot?: boolean; className?: string }) {
  const tones = {
    neutral: "bg-surface-2 text-muted border-line",
    accent: "bg-accent-soft text-accent-2 border-accent/20",
    success: "bg-success/10 text-success border-success/20",
    warning: "bg-warning/10 text-warning border-warning/20",
    danger: "bg-danger/10 text-danger border-danger/20",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1.5 h-6 px-2 rounded-md border text-xs font-medium", tones[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function StatusDot({ tone }: { tone: "success" | "warning" | "danger" | "neutral" | "accent" }) {
  const c = { success: "bg-success", warning: "bg-warning", danger: "bg-danger", neutral: "bg-faint", accent: "bg-accent" }[tone];
  return (
    <span className="relative inline-flex size-2">
      {tone === "accent" && <span className={clsx("absolute inset-0 rounded-full animate-ping opacity-60", c)} />}
      <span className={clsx("relative inline-flex size-2 rounded-full", c)} />
    </span>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={clsx(
        "h-10 w-full rounded-lg bg-surface-2 border border-line-strong px-3 text-sm placeholder:text-faint",
        "focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent-soft transition",
        className,
      )}
    />
  );
}

export function Segmented<T extends string | number>({
  value,
  onChange,
  options,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  className?: string;
}) {
  return (
    <div className={clsx("inline-flex p-1 rounded-lg bg-surface-2 border border-line", className)} role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "h-7 px-3 rounded-md text-[13px] font-medium transition",
            o.value === value ? "bg-surface-3 text-text shadow-card" : "text-muted hover:text-text",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-6 w-10 shrink-0 rounded-full transition-colors",
        checked ? "bg-accent" : "bg-surface-3 border border-line-strong",
      )}
    >
      <span
        className={clsx(
          "absolute top-1/2 -translate-y-1/2 size-4.5 rounded-full bg-white shadow transition-all",
          checked ? "left-[20px]" : "left-[3px]",
        )}
      />
    </button>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton rounded-lg", className)} />;
}

export function Empty({ icon, title, text, action }: { icon: ReactNode; title: string; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      <div className="size-12 rounded-2xl bg-surface-2 border border-line grid place-items-center text-muted mb-4">{icon}</div>
      <h3 className="font-semibold">{title}</h3>
      {text && <p className="text-sm text-muted mt-1.5 max-w-sm">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="px-1.5 h-5 inline-flex items-center rounded border border-line-strong bg-surface-2 text-[11px] text-muted font-sans">{children}</kbd>;
}
