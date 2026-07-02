import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { identityStats } from '../lib/personView';
import { collectVerifiedPlatformPhotos } from '../lib/platformAccountView';
import { resolveMediaUrl } from '../lib/displayFields';
import { formatTargetLabel, isLocalPath } from '../lib/pathDisplay';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';

export function IdentitySummaryHero() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const queryType = useInvestigationStore((s) => s.queryType);
  const uploadedPreview = useInvestigationStore((s) => s.uploadedImagePreview);
  const status = useInvestigationStore((s) => s.status);

  const platformPhotos = useMemo(
    () => (result ? collectVerifiedPlatformPhotos(result).filter((p) => p.avatarUrl) : []),
    [result],
  );

  if (status === 'idle' || !result) return null;

  const identity = result.identity_profile;
  const profile = identity ?? result.evidence_extraction?.unified_profile;
  if (!profile) return null;

  const stats = identityStats(result, query);
  const faceDetected = (result.image_correlation?.face_matches?.length ?? 0) > 0;
  const rawName = identity?.primary_name
    ?? (profile as { primary_display_name?: string }).primary_display_name;
  const displayName = rawName && !isLocalPath(rawName)
    ? rawName
    : formatTargetLabel(query, faceDetected);

  const aliases = identity?.aliases?.slice(0, 4).map((a) => a.value) ?? [];
  const photo = identity?.photos?.[0]?.value
    ?? identity?.platform_profiles?.find((p) => p.avatar_url)?.avatar_url
    ?? uploadedPreview
    ?? undefined;

  const statTiles = [
    { label: 'Accounts', value: stats.accounts },
    { label: 'Emails', value: stats.emails },
    { label: 'Phones', value: stats.phones },
    { label: 'Domains', value: stats.domains },
    { label: 'Organizations', value: stats.organizations },
    { label: 'Expansion hops', value: stats.hops },
  ];

  return (
    <div className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-violet-950/50 to-cyan-950/30 px-5 py-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-400/80">
          Who is this person?
        </p>
        <div className="mt-3 flex flex-wrap items-start gap-5">
          {photo && (
            <img
              src={photo}
              alt={displayName}
              className="h-24 w-24 rounded-xl border border-slate-700 object-cover shadow-lg"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          )}
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold text-white">{displayName}</h2>
            {aliases.length > 0 && (
              <p className="mt-1 text-sm text-slate-400">
                Also known as: {aliases.join(', ')}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {identity && (
                <Badge variant="success">{stats.confidence.toFixed(0)}% confidence</Badge>
              )}
              {queryType === 'image' && (
                <Badge variant="info">Image → Person investigation</Badge>
              )}
              {stats.leads > 0 && (
                <Badge variant="muted">{stats.leads} leads discovered</Badge>
              )}
            </div>
            {identity && (
              <div className="mt-3 max-w-md">
                <ConfidenceBar score={stats.confidence} />
              </div>
            )}
            {platformPhotos.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {platformPhotos.slice(0, 12).map((p) => {
                  const img = resolveMediaUrl(p.avatarUrl);
                  if (!img) return null;
                  return (
                    <a
                      key={p.id || `${p.platform}_${p.handle}`}
                      href={p.url?.startsWith('http') ? p.url : img}
                      target="_blank"
                      rel="noreferrer"
                      title={`${p.platformLabel} @${p.handle}`}
                      className="overflow-hidden rounded-lg border border-slate-700 transition hover:border-violet-400"
                    >
                      <img
                        src={img}
                        alt={p.platformLabel}
                        className="h-10 w-10 object-cover"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px bg-slate-800/50 sm:grid-cols-3 lg:grid-cols-6">
        {statTiles.map((tile) => (
          <div key={tile.label} className="bg-slate-900/60 px-4 py-3 text-center">
            <p className="text-lg font-bold text-cyan-300">{tile.value}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tile.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
