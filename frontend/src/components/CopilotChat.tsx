import { useEffect, useRef, useState } from 'react';
import { copilotAsk, fetchCopilotStatus, fetchCopilotSummary, prewarmCopilot } from '../api/client';
import { fetchCaseDetail } from '../api/enterprise';
import { useAuthStore } from '../store/authStore';
import { useInvestigationStore } from '../store/investigationStore';
import { useUiStore } from '../store/uiStore';
import { CopilotMessage } from './CopilotMessage';

export function CopilotChat() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [llmOnline, setLlmOnline] = useState<boolean | null>(null);
  const [modelName, setModelName] = useState('gemini-2.5-flash-lite');
  const [provider, setProvider] = useState<string>('gemini');
  const [scopeLabel, setScopeLabel] = useState<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const summaryScopeRef = useRef('');
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const status = useInvestigationStore((s) => s.status);
  const messages = useInvestigationStore((s) => s.chatMessages);
  const addChatMessage = useInvestigationStore((s) => s.addChatMessage);
  const updateChatMessage = useInvestigationStore((s) => s.updateChatMessage);
  const clearChatMessages = useInvestigationStore((s) => s.clearChatMessages);
  const selectedCaseId = useUiStore((s) => s.selectedCaseId);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const caseMeta = useUiStore((s) => s.selectedCaseMeta);
  const setSelectedCase = useUiStore((s) => s.setSelectedCase);
  /** Active case wins — matches SearchBar and where new investigations are linked. */
  const caseId = activeCaseId || selectedCaseId || undefined;

  const scopeKey = `${caseId || ''}:${investigationId || ''}:${status}`;

  useEffect(() => {
    if (!caseId) {
      setScopeLabel('');
      return;
    }
    if (caseMeta?.case_id === caseId && caseMeta.case_number) {
      setScopeLabel(caseMeta.case_number);
      return;
    }
    fetchCaseDetail(caseId)
      .then((d) => {
        setScopeLabel(d.case_number);
        setSelectedCase(caseId, { case_number: d.case_number, title: d.title });
      })
      .catch(() => setScopeLabel(caseId.slice(0, 8)));
  }, [caseId, caseMeta?.case_id, caseMeta?.case_number, setSelectedCase]);

  useEffect(() => {
    const load = () => {
      fetchCopilotStatus()
        .then((s) => {
          setLlmOnline(s.ollama_online);
          setModelName(s.model || 'gemini-2.5-flash-lite');
          setProvider(s.provider || 'ollama');
        })
        .catch(() => setLlmOnline(false));
    };
    load();
    prewarmCopilot().then((s) => {
      setLlmOnline(s.ollama_online);
      setModelName(s.model || 'grok-4.3');
      setProvider(s.provider || 'ollama');
    }).catch(() => {});
    const id = window.setInterval(load, 30000);
    return () => window.clearInterval(id);
  }, [status, investigationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading, summaryLoading]);

  useEffect(() => {
    if (summaryScopeRef.current === scopeKey) return;
    if (!caseId) {
      if (status === 'complete' && investigationId) {
        summaryScopeRef.current = scopeKey;
        clearChatMessages();
        setSummaryLoading(true);
        fetchCopilotSummary({ investigation_id: investigationId })
          .then((summary) => {
            addChatMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: summary.summary_markdown || 'No data yet.',
              timestamp: new Date().toISOString(),
            });
          })
          .catch(() => {})
          .finally(() => setSummaryLoading(false));
      }
      return;
    }

    summaryScopeRef.current = scopeKey;
    clearChatMessages();
    setSummaryLoading(true);

    fetchCopilotSummary({
      case_id: caseId,
      investigation_id: investigationId ?? undefined,
    })
      .then((summary) => {
        if (summary.case_number) setScopeLabel(summary.case_number);
        addChatMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: summary.summary_markdown || 'No verified findings yet.',
          timestamp: new Date().toISOString(),
        });
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Could not load verified summary';
        addChatMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `**Summary unavailable**\n\n${msg}\n\nSelect the case you are working on in the top bar, then reopen the copilot.`,
          timestamp: new Date().toISOString(),
        });
      })
      .finally(() => setSummaryLoading(false));
  }, [scopeKey, caseId, investigationId, status, clearChatMessages, addChatMessage]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    if (!caseId && status !== 'complete') {
      addChatMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Select an **active case** in the top bar first — the copilot only uses investigations linked to that case.',
        timestamp: new Date().toISOString(),
      });
      return;
    }

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
          investigation_id: caseId ? (investigationId ?? undefined) : (investigationId ?? undefined),
          case_id: caseId,
          context: { result: caseId ? result : result, query, case_id: caseId },
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
        `Copilot error: ${msg}\n\n${
          provider === 'gemini'
            ? 'Check GEMINI_API_KEY in .env and restart the backend.'
            : provider === 'xai'
              ? 'Check XAI_API_KEY in .env and restart the backend.'
              : 'Ensure Ollama is running:\n  ollama serve\n  ollama pull qwen2.5:3b'
        }`,
      );
    } finally {
      setLoading(false);
    }
  };

  const engineLabel = provider === 'gemini' ? 'Gemini' : provider === 'xai' ? 'Grok' : 'Ollama';
  const statusLabel =
    llmOnline === null
      ? 'Connecting…'
      : llmOnline
        ? `${modelName} · ${engineLabel}`
        : provider === 'gemini'
          ? 'Gemini offline'
          : provider === 'xai'
            ? 'Grok offline'
            : 'Ollama offline';

  const caseSubtitle = caseId
    ? scopeLabel
      ? `Active case · ${scopeLabel} · linked investigations only`
      : 'Active case · loading…'
    : 'Select a case to unlock case-wide intel';

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
            <p className="text-[10px] text-violet-300/70">{caseSubtitle}</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-medium ring-1 ${
            llmOnline
              ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25'
              : llmOnline === false
                ? 'bg-rose-500/10 text-rose-300 ring-rose-500/25'
                : 'bg-violet-500/10 text-violet-300 ring-violet-500/25'
          }`}
        >
          {statusLabel}
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pr-1">
        {!caseId && !summaryLoading && messages.length === 0 && (
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-center">
            <p className="text-xs text-amber-100/90">Select your active case in the top bar. Copilot will load only that case&apos;s investigations.</p>
          </div>
        )}
        {summaryLoading && messages.length === 0 && (
          <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 px-4 py-3 text-center">
            <p className="text-xs text-violet-200/90">
              Loading investigations for {scopeLabel || 'active case'}…
            </p>
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
        Scoped to your active case only — not other cases. Change case in the top bar to switch intel.
      </p>

      <div className="mt-2 flex gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-2 backdrop-blur-sm">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
          placeholder={caseId ? 'Ask about this case…' : 'Select a case first…'}
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
