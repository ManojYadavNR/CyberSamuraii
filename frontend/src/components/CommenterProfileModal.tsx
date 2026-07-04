import { useEffect } from 'react';

export function CommenterProfileModal({ comment, onClose }: { comment: any, onClose: () => void }) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!comment || !comment.metadata) return null;
  const meta = comment.metadata;

  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      
      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-800/50 px-5 py-3">
          <h3 className="text-sm font-semibold text-white">Commenter Profile</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-700 hover:text-white">✕</button>
        </div>
        
        <div className="p-5">
          <div className="flex items-center gap-4">
            {meta.ownerProfilePicUrl ? (
              <img src={meta.ownerProfilePicUrl} alt={meta.ownerUsername} className="h-20 w-20 rounded-full object-cover border-2 border-slate-700" />
            ) : (
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-800 text-3xl">👤</div>
            )}
            <div>
              <h2 className="text-xl font-bold text-white">@{meta.ownerUsername || 'Unknown'}</h2>
              {meta.ownerId && <p className="text-xs text-slate-400">User ID: {meta.ownerId}</p>}
              <div className="mt-2 flex gap-2">
                <a 
                  href={`https://instagram.com/${meta.ownerUsername}`} 
                  target="_blank" 
                  rel="noreferrer" 
                  className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500"
                >
                  View Profile ↗
                </a>
              </div>
            </div>
          </div>
          
          <div className="mt-6 border-t border-slate-800 pt-4">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Comment Details</h4>
            <div className="space-y-3 text-sm">
              <div className="flex gap-4">
                <span className="w-24 shrink-0 text-slate-400">Platform</span>
                <span className="capitalize text-slate-200">{meta.platform || 'Instagram'}</span>
              </div>
              <div className="flex gap-4">
                <span className="w-24 shrink-0 text-slate-400">Likes</span>
                <span className="text-slate-200">{meta.likesCount || 0}</span>
              </div>
              <div className="flex gap-4">
                <span className="w-24 shrink-0 text-slate-400">Date</span>
                <span className="text-slate-200">{new Date(meta.timestamp).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
