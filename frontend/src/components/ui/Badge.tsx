interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warn' | 'danger' | 'info' | 'muted';
  className?: string;
}

const VARIANTS = {
  default: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25',
  success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  warn: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  danger: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
  info: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
  muted: 'bg-slate-700/50 text-slate-400 border-slate-600/50',
};

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${VARIANTS[variant]} ${className}`}>
      {children}
    </span>
  );
}
