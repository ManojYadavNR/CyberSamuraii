import { useMemo, useState } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  formatPlatformHandle,
  getVerifiedPlatformDetails,
  isEmailRegistrationHandle,
  type PlatformVisual,
  type VerifiedPlatformDetail,
} from '../lib/platformAccountView';
import { flattenProbeCandidates } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';
import { EmptyState } from './ui/EmptyState';

function VisualGallery({ visuals }: { visuals: PlatformVisual[] }) {
  if (!visuals.length) {
    return (
      <p className="text-xs text-slate-500">No profile images or video previews extracted for this platform.</p>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {visuals.map((visual, idx) => (
        <a
          key={`${visual.type}_${visual.url}_${idx}`}
          href={visual.url}
          target="_blank"
          rel="noreferrer"
          className="group overflow-hidden rounded-lg border border-slate-800 bg-slate-950/60 transition hover:border-cyan-700/50"
        >
          <div className="relative aspect-square bg-slate-900">
            {visual.type === 'video' && !visual.thumbnailUrl.startsWith('http') ? (
              <div className="flex h-full items-center justify-center text-3xl text-slate-500">▶</div>
            ) : (
              <img
                src={visual.thumbnailUrl}
                alt={visual.title}
                className="h-full w-full object-cover transition group-hover:scale-105"
                loading="lazy"
                referrerPolicy="no-referrer"
                onError={(e) => {
                  const el = e.target as HTMLImageElement;
                  el.style.display = 'none';
                }}
              />
            )}
            {visual.type === 'video' && (
              <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-white">▶ Video</span>
            )}
            {visual.type === 'avatar' && (
              <span className="absolute bottom-1 right-1 rounded bg-emerald-900/80 px-1.5 py-0.5 text-[10px] text-emerald-200">Avatar</span>
            )}
          </div>
          <p className="truncate px-2 py-1.5 text-[10px] text-slate-400">{visual.title}</p>
        </a>
      ))}
    </div>
  );
}

function AttributeGroup({ group }: { group: VerifiedPlatformDetail['groups'][number] }) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-3">
      <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
        <span>{group.icon}</span>
        {group.label}
        <Badge variant="muted" className="ml-auto">{group.items.length}</Badge>
      </h4>
      <div className="space-y-2">
        {group.items.map((item, idx) => (
          <div key={`${item.label}_${idx}`} className="rounded border border-slate-800/60 bg-slate-900/50 px-2.5 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{item.label}</p>
            {item.value.startsWith('http') ? (
              <a href={item.value} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-cyan-300 hover:underline">
                {item.value}
              </a>
            ) : (
              <p className="mt-1 break-words text-sm leading-relaxed text-slate-200">{item.value}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PlatformCard({ detail }: { detail: VerifiedPlatformDetail }) {
  const [open, setOpen] = useState(true);
  const score = Math.round((detail.fusionScore ?? 0) * 100);

  return (
    <article className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-4 px-4 py-4 text-left transition hover:bg-slate-800/30"
      >
        {detail.avatarUrl ? (
          <img
            src={detail.avatarUrl}
            alt={detail.displayName || detail.handle}
            className="h-14 w-14 shrink-0 rounded-lg border border-slate-700 object-cover bg-slate-950"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-lg font-bold text-cyan-400">
            {detail.platformLabel.charAt(0)}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-white">{detail.platformLabel}</h3>
            <Badge variant="success">Verified</Badge>
            {isEmailRegistrationHandle(detail.handle) && (
              <Badge variant="info">Email registration</Badge>
            )}
            <Badge variant="info">{detail.fieldCount} fields</Badge>
            {detail.visuals.length > 0 && (
              <Badge variant="muted">{detail.visuals.length} visual{detail.visuals.length === 1 ? '' : 's'}</Badge>
            )}
          </div>
          <p className="mt-1 font-mono text-sm text-cyan-300">{formatPlatformHandle(detail.handle)}</p>
          {detail.displayName && detail.displayName !== detail.handle && (
            <p className="mt-0.5 text-sm text-slate-300">{detail.displayName}</p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className="font-mono text-sm text-emerald-400">{score}%</p>
          <p className="mt-2 text-xs text-slate-500">{open ? '▲' : '▼'}</p>
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-800/80 px-4 pb-4 pt-3 space-y-4">
          {detail.url && (
            <a href={detail.url} target="_blank" rel="noreferrer" className="inline-flex text-sm text-cyan-400 hover:underline">
              Open profile ↗
            </a>
          )}
          <div className="max-w-xs"><ConfidenceBar score={score} /></div>

          <div>
            <h4 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Visual media</h4>
            <VisualGallery visuals={detail.visuals} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {detail.groups.map((group) => (
              <AttributeGroup key={group.id} group={group} />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

export function VerifiedPlatformsPanel() {
  const result = useInvestigationStore((s) => s.result);
  const status = useInvestigationStore((s) => s.status);
  const details = useMemo(() => getVerifiedPlatformDetails(result), [result]);
  const probes = useMemo(() => flattenProbeCandidates(result), [result]);

  if (!result) return null;

  if (!details.length && !probes.length) {
    return (
      <EmptyState
        icon="🌐"
        title="No verified platform profiles yet"
        description="Verified accounts will appear here with photos, video previews, and full per-platform details."
      />
    );
  }

  return (
    <section className="space-y-4">
      {details.length > 0 && (
        <div className="intel-card overflow-hidden">
          <div className="border-b border-slate-800/80 bg-gradient-to-r from-emerald-950/30 to-cyan-950/20 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">
                  Verified Platform Accounts
                </p>
                <h2 className="mt-1 text-lg font-semibold text-white">
                  {details.length} verified platform{details.length === 1 ? '' : 's'} — full details & visuals
                </h2>
              </div>
              <Badge variant="success">{details.length} verified</Badge>
            </div>
          </div>
          <div className="space-y-3 p-4">
            {details.map((detail) => (
              <PlatformCard key={detail.entityId} detail={detail} />
            ))}
          </div>
        </div>
      )}

      {probes.length > 0 && (
        <div className="intel-card overflow-hidden">
          <div className="border-b border-amber-500/20 bg-amber-500/5 px-5 py-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-amber-300">
              {status === 'running' ? 'Live probe hits — verifying…' : 'Unverified probe hits'}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Found by username scanners; each URL is live-checked before promotion to verified cards above.
            </p>
          </div>
          <div className="grid gap-2 p-4 sm:grid-cols-2">
            {probes.slice(0, 24).map((probe) => (
              <a
                key={probe.id}
                href={probe.url.startsWith('http') ? probe.url : `https://${probe.url}`}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 transition hover:border-amber-500/30"
              >
                <p className="truncate text-sm font-medium text-slate-200">{probe.platform}</p>
                <p className="truncate font-mono text-xs text-cyan-400">{probe.handle}</p>
                <p className="mt-1 text-[10px] text-slate-500">{probe.sources.join(', ')} · {probe.status}</p>
              </a>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
