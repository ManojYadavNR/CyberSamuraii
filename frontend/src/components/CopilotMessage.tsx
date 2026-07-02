import type { ReactNode } from 'react';

function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|<?https?:\/\/[^\s<>)\]]+>?)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const chunk = m[0];
    if (chunk.startsWith('**')) {
      parts.push(
        <strong key={`${m.index}-b`} className="font-semibold text-violet-100">
          {chunk.slice(2, -2)}
        </strong>,
      );
    } else {
      const md = /\[([^\]]+)\]\(([^)]+)\)/.exec(chunk);
      if (md) {
        parts.push(
          <a
            key={`${m.index}-a`}
            href={md[2]}
            target="_blank"
            rel="noreferrer"
            className="break-all text-cyan-300 underline decoration-cyan-500/40 underline-offset-2 hover:text-cyan-200"
          >
            {md[1]}
          </a>,
        );
      } else {
        const href = chunk.replace(/^<|>$/g, '');
        if (href.startsWith('http') && !href.includes('{')) {
          parts.push(
            <a
              key={`${m.index}-u`}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="break-all text-cyan-300 underline decoration-cyan-500/40 underline-offset-2 hover:text-cyan-200"
            >
              {href}
            </a>,
          );
        } else {
          parts.push(chunk);
        }
      }
    }
    last = m.index + chunk.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length ? parts : [text];
}

export function CopilotMessage({ content, role }: { content: string; role: 'user' | 'assistant' }) {
  if (role === 'user') {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  const lines = content.split('\n');
  const nodes: ReactNode[] = [];

  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) {
      nodes.push(<div key={`sp-${i}`} className="h-1.5" />);
      return;
    }
    if (trimmed.startsWith('## ')) {
      nodes.push(
        <h4 key={`h-${i}`} className="mb-1 mt-2 text-[11px] font-semibold uppercase tracking-wide text-violet-300/90 first:mt-0">
          {trimmed.slice(3)}
        </h4>,
      );
      return;
    }
    if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
      nodes.push(
        <div key={`li-${i}`} className="flex gap-2 pl-0.5 text-[12px] leading-relaxed text-slate-200/95">
          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-violet-400/80" />
          <span className="min-w-0 break-words">{renderInline(trimmed.replace(/^[-•]\s*/, ''))}</span>
        </div>,
      );
      return;
    }
    nodes.push(
      <p key={`p-${i}`} className="text-[12px] leading-relaxed text-slate-200/95">
        {renderInline(trimmed)}
      </p>,
    );
  });

  return <div className="space-y-0.5">{nodes}</div>;
}
