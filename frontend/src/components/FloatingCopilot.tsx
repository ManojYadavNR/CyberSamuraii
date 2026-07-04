import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { prewarmCopilot } from '../api/client';
import { CopilotChat } from './CopilotChat';

export function FloatingCopilot() {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const openCopilot = () => {
    setOpen(true);
    prewarmCopilot().catch(() => {});
  };

  if (!mounted) return null;

  return createPortal(
    <>
      {!open && (
        <button
          type="button"
          onClick={openCopilot}
          onMouseEnter={() => prewarmCopilot().catch(() => {})}
          className="floating-copilot-fab group flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 via-fuchsia-600 to-indigo-600 text-2xl shadow-2xl shadow-violet-900/50 ring-1 ring-white/20 transition hover:scale-105 hover:shadow-violet-700/60"
          title="Open Intelligence Copilot"
          aria-label="Open Intelligence Copilot"
        >
          <span className="transition group-hover:scale-110">🧠</span>
        </button>
      )}

      {open && (
        <div
          className={`floating-copilot-panel flex flex-col overflow-hidden border border-white/10 shadow-2xl shadow-black/60 backdrop-blur-xl transition-all ${
            expanded
              ? 'floating-copilot-panel--expanded'
              : ''
          }`}
          style={{
            background:
              'linear-gradient(165deg, rgba(18, 12, 32, 0.97) 0%, rgba(12, 10, 24, 0.98) 45%, rgba(8, 14, 28, 0.99) 100%)',
          }}
        >
          <div
            className="pointer-events-none absolute inset-0 opacity-40"
            style={{
              background:
                'radial-gradient(ellipse 70% 50% at 20% 0%, rgba(139, 92, 246, 0.25), transparent), radial-gradient(ellipse 50% 40% at 100% 100%, rgba(6, 182, 212, 0.12), transparent)',
            }}
          />

          <div className="relative flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500/30 to-cyan-500/20 text-base ring-1 ring-white/10">
                🧠
              </span>
              <span className="text-sm font-semibold tracking-tight text-white">Intelligence Copilot</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="rounded-lg px-2.5 py-1.5 text-[11px] text-slate-400 transition hover:bg-white/5 hover:text-violet-300"
                title={expanded ? 'Restore window size' : 'Expand to full workspace'}
              >
                {expanded ? '⊟' : '⊞'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  setExpanded(false);
                }}
                className="rounded-lg px-2.5 py-1.5 text-[11px] text-slate-400 transition hover:bg-white/5 hover:text-rose-300"
                aria-label="Close copilot"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="relative min-h-0 flex-1 overflow-hidden p-4">
            <CopilotChat />
          </div>
        </div>
      )}
    </>,
    document.body,
  );
}
