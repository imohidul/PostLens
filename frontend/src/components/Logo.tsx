export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="pl-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#9B8CFF" />
          <stop offset="1" stopColor="#4F46E5" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#pl-g)" />
      <circle cx="14.5" cy="14.5" r="6.5" fill="none" stroke="#fff" strokeWidth="2.6" />
      <path d="M19.5 19.5l5 5" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="14.5" cy="14.5" r="2.2" fill="#fff" />
    </svg>
  );
}

export function FacebookGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M24 12.07C24 5.41 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.04V9.41c0-3.02 1.8-4.7 4.54-4.7 1.31 0 2.68.24 2.68.24v2.97h-1.5c-1.5 0-1.96.93-1.96 1.89v2.26h3.32l-.53 3.5h-2.8V24C19.62 23.1 24 18.1 24 12.07" />
    </svg>
  );
}
