import { useState } from 'react';
import { copilotChat } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';

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
  const messages = useInvestigationStore((s) => s.chatMessages);
  const addChatMessage = useInvestigationStore((s) => s.addChatMessage);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg = { id: crypto.randomUUID(), role: 'user' as const, content: text, timestamp: new Date().toISOString() };
    addChatMessage(userMsg);
    setInput('');
    setLoading(true);
    try {
      const res = await copilotChat({
        message: text,
        investigation_id: investigationId ?? undefined,
        context: { result, query },
      });
      addChatMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.answer,
        timestamp: new Date().toISOString(),
      });
    } catch {
      addChatMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Copilot unavailable. Ensure backend is running.',
        timestamp: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-1">
        {messages.length === 0 && (
          <div className="text-sm text-slate-500">
            Ask the copilot about your investigation. Try:
            <div className="mt-2 flex flex-wrap gap-1">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300 hover:bg-slate-700"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`rounded-lg px-3 py-2 text-sm ${
              m.role === 'user' ? 'ml-8 bg-blue-600/20 text-blue-100' : 'mr-8 bg-slate-800 text-slate-300'
            }`}
          >
            <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
          </div>
        ))}
        {loading && <div className="text-xs text-slate-500 animate-pulse">Analyzing…</div>}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(input)}
          placeholder="Ask about linked accounts, evidence, clusters…"
          className="flex-1 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-blue-500"
        />
        <button
          onClick={() => send(input)}
          disabled={loading}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
