import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  hasPhoneIntel,
  parseSeedPhone,
  phoneMetadataFromResult,
  phoneRegistrationsFromResult,
  phoneSocialLinksFromResult,
  phoneToolStatuses,
  phoneWebHitsFromResult,
} from '../lib/phoneIntelView';
import { openLinkLabel } from '../lib/platformUtils';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

export function PhoneIntelPanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);
  const queryType = useInvestigationStore((s) => s.queryType);
  const status = useInvestigationStore((s) => s.status);
  const toolProgress = useInvestigationStore((s) => s.toolProgress);

  const seedPhone = useMemo(() => parseSeedPhone(query), [query]);
  const show = useMemo(
    () => queryType === 'phone' || queryType === 'infra' || hasPhoneIntel(result, query),
    [queryType, result, query],
  );
  const metadata = useMemo(() => phoneMetadataFromResult(result, query), [result, query]);
  const registrations = useMemo(
    () => phoneRegistrationsFromResult(result, seedPhone),
    [result, seedPhone],
  );
  const socialLinks = useMemo(() => phoneSocialLinksFromResult(result), [result]);
  const webHits = useMemo(() => phoneWebHitsFromResult(result), [result]);
  const toolStatuses = useMemo(() => phoneToolStatuses(result), [result]);

  const hasContent = Boolean(
    metadata || registrations.length > 0 || socialLinks.length > 0 || webHits.length > 0,
  );

  if (!show) return null;

  const phoneToolRunning = toolProgress.some(
    (t) => (t.tool === 'phone_social_intel' || t.tool === 'phoneinfoga') && t.status === 'running',
  );
  const waiting = status === 'running' && !hasContent && (phoneToolRunning || !result);

  if (!result && !waiting) return null;

  if (waiting) {
    return (
      <section className="intel-card overflow-hidden p-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">Phone intelligence</p>
        <h2 className="mt-1 text-lg font-semibold text-white">{seedPhone || query}</h2>
        <p className="mt-2 text-sm text-slate-400">
          Running carrier lookup, platform registration checks, and web footprint search…
        </p>
      </section>
    );
  }

  if (!result) return null;

  if (!hasContent && !seedPhone) {
    return (
      <EmptyState
        icon="📱"
        title="No phone intelligence yet"
        description="Enter a phone number to run PhoneInfoga carrier lookup and social registration checks."
      />
    );
  }

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-emerald-950/40 to-cyan-950/30 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">
          Phone intelligence
        </p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          {metadata?.phone || seedPhone || 'Phone branch'}
        </h2>
        {metadata && (
          <p className="mt-1 text-xs text-slate-400">
            {[
              metadata.carrier && `Carrier: ${metadata.carrier}`,
              metadata.location && `Location: ${metadata.location}`,
              metadata.lineType && `Line: ${metadata.lineType}`,
              metadata.valid === true && 'Validated number',
              metadata.valid === false && 'Invalid number format',
            ].filter(Boolean).join(' · ')}
          </p>
        )}
      </div>

      <div className="space-y-4 p-5">
        {toolStatuses.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Phone branch tools</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {toolStatuses.map((tool) => (
                <div key={tool.tool} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-200">{tool.label}</span>
                    <Badge variant={tool.status === 'completed' ? 'success' : 'danger'}>
                      {tool.status.replace('_', ' ')}
                    </Badge>
                  </div>
                  {tool.detail && <p className="mt-1 text-[11px] text-slate-500">{tool.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {metadata && (metadata.carrier || metadata.location || metadata.countryCode || metadata.countryName || metadata.lineType || metadata.valid != null) && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Number details</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {metadata.carrier && (
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500">Carrier</p>
                  <p className="text-sm text-slate-200">{metadata.carrier}</p>
                </div>
              )}
              {metadata.location && (
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500">Location</p>
                  <p className="text-sm text-slate-200">{metadata.location}</p>
                </div>
              )}
              {(metadata.countryName || metadata.countryCode) && (
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500">Country</p>
                  <p className="text-sm text-slate-200">
                    {metadata.countryName || `+${metadata.countryCode}`}
                  </p>
                </div>
              )}
              {metadata.lineType && (
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500">Line type</p>
                  <p className="text-sm text-slate-200">{metadata.lineType}</p>
                </div>
              )}
              {metadata.valid != null && (
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500">Validation</p>
                  <p className="text-sm text-slate-200">{metadata.valid ? 'Valid mobile number' : 'Invalid'}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {registrations.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Registered on platforms ({registrations.length})
            </h3>
            <p className="mb-3 text-xs text-slate-500">
              Platforms where the number is registered or linked (ignorant + profile resolution).
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {registrations.map((reg) => (
                <div
                  key={reg.id}
                  className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-200">{reg.platformLabel}</span>
                    <Badge variant={reg.status === 'registered' ? 'success' : 'info'}>
                      {reg.status === 'registered' ? 'Registered' : 'Linked'}
                    </Badge>
                  </div>
                  <p className="mt-1 font-mono text-xs text-cyan-300">{reg.phone}</p>
                  {reg.url && (
                    <a
                      href={reg.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block truncate text-[11px] text-cyan-400 hover:underline"
                    >
                      {openLinkLabel(reg.url)}
                    </a>
                  )}
                  <p className="mt-1 text-[10px] text-slate-500">{reg.source}{reg.method ? ` · ${reg.method}` : ''}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {socialLinks.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Social profile links ({socialLinks.length})
            </h3>
            <div className="space-y-2">
              {socialLinks.map((link) => (
                <div key={link.id} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-slate-200">{link.platformLabel}</span>
                    <Badge variant="muted">{link.status}</Badge>
                  </div>
                  {link.title && <p className="mt-1 text-sm text-slate-300">{link.title}</p>}
                  {link.url && (
                    <a href={link.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-cyan-400 hover:underline">
                      {openLinkLabel(link.url)}
                    </a>
                  )}
                  {link.snippet && <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{link.snippet}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {webHits.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Web footprint ({webHits.length})
            </h3>
            <div className="space-y-2">
              {webHits.slice(0, 12).map((hit) => (
                <div key={hit.id} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <a href={hit.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-cyan-300 hover:underline">
                    {hit.title || hit.url}
                  </a>
                  {hit.snippet && <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{hit.snippet}</p>}
                  <p className="mt-1 text-[10px] text-slate-600">{hit.source} · {hit.category}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
