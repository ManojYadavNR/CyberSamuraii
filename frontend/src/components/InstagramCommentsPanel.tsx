import { useMemo, useState } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { CommenterProfileModal } from './CommenterProfileModal';

export function InstagramCommentsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const [selectedCommenter, setSelectedCommenter] = useState<any>(null);

  const comments = useMemo(() => {
    return (result?.fusion?.deduplicated_entities || []).filter(e => e.type === 'comment' || e.metadata?.is_comment);
  }, [result]);

  if (!result || comments.length === 0) return null;

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-purple-950/40 via-slate-900 to-indigo-950/40 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-purple-400/90">Instagram Comments Intelligence</p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          Analyzed Comments ({comments.length})
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Extracted social media comments and linked profiles.
        </p>
      </div>
      
      <div className="divide-y divide-slate-800/60 p-5">
        {comments.map((comment: any, i: number) => {
          const meta = comment.metadata || {};
          const owner = meta.ownerUsername || 'Unknown';
          const pic = meta.ownerProfilePicUrl;
          const url = meta.postUrl;
          
          return (
            <div key={i} className="py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-start gap-4">
                {pic ? (
                  <img src={pic} alt={owner} className="h-10 w-10 shrink-0 rounded-full object-cover" />
                ) : (
                  <span className="text-xl shrink-0">💬</span>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <button 
                      onClick={() => setSelectedCommenter(comment)}
                      className="text-sm font-semibold text-cyan-400 hover:underline"
                    >
                      @{owner}
                    </button>
                    <span className="text-[10px] text-slate-500">{new Date(meta.timestamp).toLocaleDateString()}</span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">
                    {comment.value}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <span className="inline-flex items-center rounded bg-slate-800/50 px-2 py-0.5 text-[10px] font-medium text-slate-400 border border-slate-700/50">
                      {meta.platform || 'instagram'}
                    </span>
                    {url && (
                      <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center rounded bg-slate-800/50 px-2 py-0.5 text-[10px] font-medium text-blue-400 border border-slate-700/50 hover:bg-slate-700">
                        View Post ↗
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      
      {selectedCommenter && (
        <CommenterProfileModal 
          comment={selectedCommenter} 
          onClose={() => setSelectedCommenter(null)} 
        />
      )}
    </section>
  );
}
