import { useState } from 'react';
import { copilotChat } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { buildAiSummary } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';

const SUGGESTIONS = [
  'show linked accounts',
  'summarize suspect activity',
  'why is this cluster suspicious?',
  'show evidence breakdown',
];

export function CopilotChat() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const investigationId = useInvestigationStore((s) => s.investigationId);
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const status = useInvestigationStore((s) => s.status);
  const messages = useInvestigationStore((s) => s.chatMessages);
  const addChatMessage = useInvestigationStore((s) => s.addChatMessage);

  const aiSummary = buildAiSummary(result, query);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    addChatMessage({ id: crypto.randomUUID(), role: 'user', content: text, timestamp: new Date().toISOString() });
    setInput('');
    setLoading(true);
    try {
      const res = await copilotChat({
        message: text,
        investigation_id: investigationId ?? undefined,
        context: { result, query },
      });
      addChatMessage({ id: crypto.randomUUID(), role: 'assistant', content: res.answer, timestamp: new Date().toISOString() });
    } catch {
      addChatMessage({ id: crypto.randomUUID(), role: 'assistant', content: 'Intelligence copilot offline. Verify backend connection.', timestamp: new Date().toISOString() });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center gap-2 border-b border-slate-800 pb-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 text-sm">🧠</div>
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Intelligence Copilot</h3>
          <p className="text-[10px] text-slate-500">AI-assisted case analysis</p>
        </div>
      </div>

      {status === 'complete' && result && (
        <div className="mb-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3">
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="info">AI Summary</Badge>
          </div>
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{aiSummary}</p>
        </div>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && status !== 'complete' && (
          <p className="text-xs text-slate-500">Complete an investigation or ask a question below.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[90%] rounded-2xl px-3 py-2 text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'rounded-br-sm bg-blue-600/30 text-blue-100'
                  : 'rounded-bl-sm border border-slate-800 bg-slate-800/60 text-slate-300'
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-1 px-2">
            <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-500 [animation-delay:0ms]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-500 [animation-delay:150ms]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-500 [animation-delay:300ms]" />
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-700/60 bg-slate-800/40 px-2.5 py-1 text-[10px] text-slate-400 hover:border-cyan-500/30 hover:text-cyan-300">
            {s}
          </button>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(input)}
          placeholder="Ask intelligence question…"
          className="intel-input flex-1 py-2 text-xs"
        />
        <button onClick={() => send(input)} disabled={loading} className="intel-btn-primary px-4 py-2 text-xs">
          Send
        </button>
      </div>
    </div>
  );
}
