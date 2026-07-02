import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  displayableEmails,
  emailDorkHitsFromResult,
  emailRegistrationsFromResult,
  emailToolStatuses,
  ghuntFromResult,
  hasEmailIntel,
  holeheScanSummary,
  parseSeedEmail,
} from '../lib/emailIntelView';
import { openLinkLabel, platformLabel } from '../lib/platformUtils';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

export function EmailIntelPanel() {
  const result = useInvestigationStore((s) => s.result);
  const query = useInvestigationStore((s) => s.query);

  const seedEmail = useMemo(() => parseSeedEmail(query), [query]);
  const show = useMemo(() => hasEmailIntel(result, query), [result, query]);
  const emails = useMemo(() => displayableEmails(result, query), [result, query]);
  const registrations = useMemo(
    () => emailRegistrationsFromResult(result, seedEmail),
    [result, seedEmail],
  );
  const holehe = useMemo(() => holeheScanSummary(result), [result]);
  const toolStatuses = useMemo(() => emailToolStatuses(result), [result]);
  const dorkHits = useMemo(() => emailDorkHitsFromResult(result, query), [result, query]);
  const ghunt = useMemo(() => ghuntFromResult(result), [result]);
  const gravatar = useMemo(
    () => (result?.public_profile_data ?? []).filter((p) => p.source === 'gravatar' || p.platform === 'gravatar'),
    [result],
  );
  const leads = useMemo(() => result?.investigation_leads ?? [], [result]);

  if (!result || !show) return null;

  if (!seedEmail && !emails.length && !registrations.length && !gravatar.length) {
    return (
      <EmptyState
        icon="✉️"
        title="No email intelligence yet"
        description="Include an email in your search (e.g. username | email@domain.com) to run Holehe registration checks."
      />
    );
  }

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-sky-950/40 to-violet-950/30 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-400/80">
          Email intelligence
        </p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          {seedEmail || emails[0] || 'Email branch'}
        </h2>
        {holehe && (
          <p className="mt-1 text-xs text-slate-400">
            Holehe scanned {holehe.sitesChecked ?? '?'} sites
            {holehe.verified != null ? ` · ${holehe.verified} live registration(s) for this email` : ''}
          </p>
        )}
      </div>

      <div className="space-y-4 p-5">
        {toolStatuses.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Email branch tools</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {toolStatuses.map((tool) => (
                <div key={tool.tool} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-200">{tool.label}</span>
                    <Badge variant={tool.status === 'found' || tool.status === 'completed' ? 'success' : tool.status === 'skipped' ? 'warn' : 'muted'}>
                      {tool.status.replace('_', ' ')}
                    </Badge>
                  </div>
                  {tool.detail && <p className="mt-1 text-[11px] text-slate-500">{tool.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {emails.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Email address(es)</h3>
            <div className="flex flex-wrap gap-2">
              {emails.map((email) => (
                <Badge key={email} variant="info">{email}</Badge>
              ))}
            </div>
          </div>
        )}

        {registrations.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Live email registrations ({registrations.length})
            </h3>
            <p className="mb-3 text-xs text-slate-500">
              Platforms where Holehe confirmed this email is registered — separate from username profile hits.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {registrations.map((reg) => (
                <div
                  key={reg.id}
                  className="rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-200">{reg.platformLabel}</span>
                    <Badge variant="success">Registered</Badge>
                  </div>
                  <p className="mt-1 font-mono text-xs text-cyan-300">{reg.email}</p>
                  <p className="mt-1 text-[10px] text-slate-500">{reg.source} · {reg.platform}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {registrations.length === 0 && holehe && (
          <p className="text-sm text-slate-400">
            Holehe completed but found no additional live registrations to promote for this email on top of username results.
            Consumer Gmail addresses often have few public registrations.
          </p>
        )}

        {gravatar.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Gravatar profile</h3>
            {gravatar.map((profile, idx) => (
              <div key={idx} className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-300">
                {String(profile.display_name ?? profile.profile_url ?? 'Gravatar linked')}
                {typeof profile.avatar_url === 'string' && profile.avatar_url && (
                  <img src={profile.avatar_url} alt="" className="mt-2 h-12 w-12 rounded-full border border-slate-700" />
                )}
                {Array.isArray(profile.accounts) && profile.accounts.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    Linked: {(profile.accounts as Array<{ domain?: string }>).map((a) => a.domain).filter(Boolean).join(', ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {ghunt?.found && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Google account (GHunt)</h3>
            <p className="text-sm text-slate-300">Public Google account metadata linked to this email.</p>
            {ghunt.metadata && (
              <pre className="mt-2 max-h-40 overflow-auto rounded border border-slate-800 bg-slate-950/60 p-2 text-[10px] text-slate-400">
                {JSON.stringify(ghunt.metadata, null, 2)}
              </pre>
            )}
          </div>
        )}

        {dorkHits.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Email Google dork hits ({dorkHits.length})
            </h3>
            <p className="mb-3 text-xs text-slate-500">
              Web pages mentioning this email — Gmail-specific dorks, pastes, dev profiles, and public documents.
            </p>
            <div className="space-y-2">
              {dorkHits.map((hit) => (
                <a
                  key={hit.id}
                  href={hit.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-violet-500/20 bg-violet-500/5 px-3 py-2.5 transition hover:border-violet-400/40"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium text-slate-200 line-clamp-1">{hit.title}</span>
                    <Badge variant="info">{hit.category.replace(/_/g, ' ')}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-cyan-400/80">{openLinkLabel(hit.url)} · {hit.platform}</p>
                  {hit.snippet && <p className="mt-1 text-xs text-slate-500 line-clamp-2">{hit.snippet}</p>}
                </a>
              ))}
            </div>
          </div>
        )}

        {leads.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Inconclusive checks ({leads.length})
            </h3>
            <p className="mb-2 text-xs text-slate-500">Rate-limited or blocked — verify manually if relevant.</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {leads.slice(0, 8).map((lead, idx) => (
                <div key={idx} className="rounded border border-amber-500/20 bg-amber-500/5 px-2 py-1.5 text-xs text-slate-400">
                  {platformLabel(String(lead.platform ?? 'web'))} · {String(lead.reason ?? 'inconclusive')}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
