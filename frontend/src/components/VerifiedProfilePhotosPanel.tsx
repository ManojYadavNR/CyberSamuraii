import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { collectVerifiedPlatformPhotos } from '../lib/platformAccountView';
import { resolveMediaUrl, externalPageUrl } from '../lib/mediaUrl';
import { Badge } from './ui/Badge';

export function VerifiedProfilePhotosPanel() {
  const result = useInvestigationStore((s) => s.result);
  const photos = useMemo(() => collectVerifiedPlatformPhotos(result), [result]);

  const withImage = photos.filter((p) => p.avatarUrl);
  const missing = photos.filter((p) => !p.avatarUrl);

  if (!photos.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/20 p-6 text-center text-sm text-slate-500">
        No verified platform accounts yet — run username tools (Sherlock, Maigret, Social Analyzer) to discover profiles.
      </div>
    );
  }

  return (
    <section className="intel-card min-w-0 overflow-hidden">
      <div className="border-b border-violet-500/20 bg-gradient-to-r from-violet-950/40 to-cyan-950/20 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-300/90">
          Person identification
        </p>
        <h3 className="mt-1 text-lg font-semibold text-white">Verified profile photos</h3>
        <p className="mt-1 text-xs text-slate-400">
          {withImage.length} of {photos.length} verified platform{photos.length === 1 ? '' : 's'} with a profile image
          — compare faces and avatars to confirm identity.
        </p>
      </div>

      <div className="p-5">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {photos.map((card) => {
            const img = resolveMediaUrl(card.avatarUrl);
            const profileUrl = card.url?.startsWith('http') ? card.url : undefined;
            return (
              <article
                key={card.id || `${card.platform}_${card.handle}`}
                className="group overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60 transition hover:border-violet-500/40"
              >
                <div className="relative aspect-square bg-slate-900">
                  {img ? (
                    <a
                      href={profileUrl ?? externalPageUrl(card.avatarUrl) ?? '#'}
                      target="_blank"
                      rel="noreferrer"
                      title="Open profile"
                      className="block h-full w-full"
                      onClick={(e) => { if (!profileUrl && !externalPageUrl(card.avatarUrl)) e.preventDefault(); }}
                    >
                      <img
                        src={img}
                        alt={`${card.platformLabel} ${card.handle}`}
                        className="h-full w-full object-cover transition group-hover:scale-105"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          const el = e.target as HTMLImageElement;
                          el.style.display = 'none';
                        }}
                      />
                    </a>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-1 p-2 text-center">
                      <span className="text-2xl font-bold text-slate-600">{card.platformLabel.charAt(0)}</span>
                      <span className="text-[9px] text-slate-600">No photo</span>
                    </div>
                  )}
                  <span className="absolute bottom-1 left-1 rounded bg-black/75 px-1.5 py-0.5 text-[9px] font-semibold text-white">
                    {card.platformLabel}
                  </span>
                </div>
                <div className="space-y-1 p-2">
                  <p className="truncate font-mono text-[11px] text-cyan-300">@{card.handle}</p>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="success" className="text-[8px]">Verified</Badge>
                    {card.sources.slice(0, 2).map((src) => (
                      <Badge key={src} variant="muted" className="text-[8px]">{src}</Badge>
                    ))}
                  </div>
                  {profileUrl && (
                    <a
                      href={profileUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="block truncate text-[10px] text-slate-500 hover:text-cyan-400"
                    >
                      Open profile ↗
                    </a>
                  )}
                </div>
              </article>
            );
          })}
        </div>

        {missing.length > 0 && (
          <p className="mt-4 text-xs text-slate-500">
            {missing.length} verified platform{missing.length === 1 ? '' : 's'} without a public profile image
            ({missing.map((m) => m.platformLabel).slice(0, 6).join(', ')}
            {missing.length > 6 ? '…' : ''}) — deep enrichment may still be running or the site blocks photos.
          </p>
        )}
      </div>
    </section>
  );
}
