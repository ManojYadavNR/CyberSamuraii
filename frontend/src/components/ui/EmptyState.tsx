export function EmptyState({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-700/80 bg-slate-900/30 px-8 py-12 text-center">
      <div className="mb-4 text-4xl opacity-40">{icon}</div>
      <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
      <p className="mt-2 max-w-sm text-xs leading-relaxed text-slate-500">{description}</p>
    </div>
  );
}
