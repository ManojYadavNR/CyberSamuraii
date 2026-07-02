import { useEffect, useRef, useState } from 'react';
import { copilotAsk, fetchCopilotStatus, prewarmCopilot } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { CopilotMessage } from './CopilotMessage';

export function CopilotChat() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null);
  const [modelName, setModelName] = useState('qwen2.5:3b');
  const scrollRef = useRef<HTMLDivElement>(null);
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const status = useInvestigationStore((s) => s.status);
  const messages = useInvestigationStore((s) => s.chatMessages);
  const addChatMessage = useInvestigationStore((s) => s.addChatMessage);
  const updateChatMessage = useInvestigationStore((s) => s.updateChatMessage);

  useEffect(() => {
    const load = () => {
      fetchCopilotStatus()
        .then((s) => {
          setOllamaOnline(s.ollama_online);
          setModelName(s.model || 'qwen2.5:3b');
        })
        .catch(() => setOllamaOnline(false));
    };
    load();
    prewarmCopilot().then((s) => {
      setOllamaOnline(s.ollama_online);
      setModelName(s.model || 'qwen2.5:3b');
    }).catch(() => {});
    const id = window.setInterval(load, 30000);
    return () => window.clearInterval(id);
  }, [status, investigationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    addChatMessage({ id: crypto.randomUUID(), role: 'user', content: text, timestamp: new Date().toISOString() });
    setInput('');
    setLoading(true);

    const assistantId = crypto.randomUUID();
    addChatMessage({ id: assistantId, role: 'assistant', content: '', timestamp: new Date().toISOString() });

    try {
      let streamed = '';
      await copilotAsk(
        {
          message: text,
          investigation_id: investigationId ?? undefined,
          context: { result, query },
        },
        (event) => {
          if (event.status === 'thinking' && !streamed) {
            updateChatMessage(assistantId, '▍');
          }
          if (event.token) {
            streamed += event.token;
            updateChatMessage(assistantId, streamed);
          }
          if (event.done && event.answer && !streamed) {
            updateChatMessage(assistantId, event.answer);
          }
        },
      );
      if (!streamed) {
        const last = useInvestigationStore.getState().chatMessages.find((m) => m.id === assistantId);
        if (!last?.content || last.content === '▍') {
          updateChatMessage(assistantId, 'No response from copilot.');
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      updateChatMessage(
        assistantId,
        `Copilot error: ${msg}\n\nEnsure Ollama is running:\n  ollama serve\n  ollama pull qwen2.5:3b`,
      );
    } finally {
      setLoading(false);
    }
  };

  const statusLabel =
    ollamaOnline === null
      ? 'Connecting…'
      : ollamaOnline
        ? `${modelName} · streaming`
        : 'Ollama offline';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/30 via-fuchsia-500/20 to-cyan-500/30 ring-1 ring-white/10">
            <span className="text-lg">🧠</span>
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#12101f] bg-emerald-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-white">Intelligence Copilot</h3>
            <p className="text-[10px] text-violet-300/70">Investigation assistant</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-medium ring-1 ${
            ollamaOnline
              ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25'
              : ollamaOnline === false
                ? 'bg-rose-500/10 text-rose-300 ring-rose-500/25'
                : 'bg-violet-500/10 text-violet-300 ring-violet-500/25'
          }`}
        >
          {statusLabel}
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pr-1">
        {messages.length === 0 && status !== 'complete' && (
          <div className="rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3 text-center">
            <p className="text-xs text-slate-400">Ask questions here after an investigation completes.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex gap-2.5 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs ${
                m.role === 'user'
                  ? 'bg-gradient-to-br from-violet-600 to-indigo-600 text-white'
                  : 'bg-white/5 text-violet-300 ring-1 ring-white/10'
              }`}
            >
              {m.role === 'user' ? 'You' : 'AI'}
            </div>
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${
                m.role === 'user'
                  ? 'rounded-tr-md bg-gradient-to-br from-violet-600/90 to-indigo-600/80 text-white shadow-lg shadow-violet-900/30'
                  : 'rounded-tl-md border border-white/[0.08] bg-white/[0.04] text-slate-200 backdrop-blur-sm'
              }`}
            >
              {m.content === '▍' ? (
                <span className="inline-block animate-pulse text-violet-300">▍</span>
              ) : (
                <CopilotMessage content={m.content} role={m.role} />
              )}
            </div>
          </div>
        ))}
        {loading && messages[messages.length - 1]?.content === '' && (
          <div className="flex items-center gap-2 pl-9">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:0ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-fuchsia-400 [animation-delay:120ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-400 [animation-delay:240ms]" />
            <span className="text-[10px] text-slate-500">Thinking…</span>
          </div>
        )}
      </div>

      <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
        Ask anything about this case — accounts, Instagram, college, evidence, and more.
      </p>

      <div className="mt-2 flex gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-2 backdrop-blur-sm">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
          placeholder="Ask an intelligence question…"
          className="min-w-0 flex-1 rounded-lg border-0 bg-transparent px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 outline-none focus:ring-0"
        />
        <button
          type="button"
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          className="shrink-0 rounded-lg bg-gradient-to-r from-violet-600 via-fuchsia-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-violet-900/40 transition hover:from-violet-500 hover:via-fuchsia-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
