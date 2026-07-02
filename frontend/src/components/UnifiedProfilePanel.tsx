import { useInvestigationStore } from '../store/investigationStore';
import type { FieldProvenance, UnifiedPersonProfile } from '../types';
import { isDisplayableEmailField } from '../lib/accountVerification';
import { formatTargetLabel, isLocalPath } from '../lib/pathDisplay';
import { getVerifiedPlatformDetails } from '../lib/platformAccountView';
import { totalSourceCount, verifiedPlatformCount } from '../lib/profileStats';
import { Badge } from './ui/Badge';

function ProvenanceList({ label, items }: { label: string; items: FieldProvenance[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">{label} ({items.length})</h4>
      <div className="space-y-1">
        {items.slice(0, 8).map((fp, idx) => (
          <div key={`${fp.field}_${fp.value}_${fp.source_tool ?? 'src'}_${idx}`} className="rounded border border-slate-800/80 bg-slate-900/40 px-2 py-1.5">
            <p className="text-sm text-slate-200">{fp.value}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {fp.source_platform && <Badge variant="muted">{fp.source_platform}</Badge>}
              {fp.source_tool && <Badge variant="muted">{fp.source_tool}</Badge>}
              {fp.confidence != null && <Badge variant="info">{(fp.confidence * 100).toFixed(0)}%</Badge>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function UnifiedProfilePanel() {
  const result = useInvestigationStore((s) => s.result);
  const identity = result?.identity_profile;
  const profile = identity ?? result?.evidence_extraction?.unified_profile;

  if (!profile) return null;

  const isIdentity = !!identity;
  const confidence = isIdentity ? (identity.confidence_score * 100) : 0;
  const rawName = isIdentity ? identity.primary_name : (profile as { primary_display_name?: string }).primary_display_name;
  const faceDetected = (result?.image_correlation?.face_matches?.length ?? 0) > 0;
  const seedFallback = (profile as { seed_query?: string }).seed_query ?? '';
  const displayName = rawName && !isLocalPath(rawName)
    ? rawName
    : formatTargetLabel(seedFallback, faceDetected);
  const platformCount = verifiedPlatformCount(result);
  const totalPlatforms = totalSourceCount(result);
  const verifiedPlatforms = getVerifiedPlatformDetails(result);

  const unified = !isIdentity ? (profile as UnifiedPersonProfile) : undefined;
  const fields = [
    { label: 'Display Name', value: displayName },
    { label: 'Bio', value: isIdentity ? identity.primary_bio : unified?.primary_bio },
    { label: 'Location', value: isIdentity ? identity.primary_location : unified?.primary_location },
    { label: 'Email', value: (isIdentity ? identity.emails : unified?.emails)?.filter(isDisplayableEmailField)?.[0]?.value },
    { label: 'Website', value: (isIdentity ? identity.websites : unified?.websites)?.[0]?.value },
    { label: 'Organization', value: (isIdentity ? identity.organizations : unified?.organizations)?.[0]?.value },
    { label: 'Phone', value: identity?.phones?.[0]?.value },
  ].filter((f) => f.value);

  return (
    <div className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-violet-950/40 to-cyan-950/30 px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-400/80">Unified Person Profile</p>
            <h2 className="mt-1 text-lg font-semibold text-white">
              {displayName}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {isIdentity && <Badge variant="success">{(confidence).toFixed(0)}% identity confidence</Badge>}
            <Badge variant="info">{platformCount} verified platforms</Badge>
            <Badge variant="muted">{totalPlatforms} total sources</Badge>
            {isIdentity && <Badge variant="muted">{identity.total_evidence_fields} evidence fields</Badge>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {fields.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {fields.map((f) => (
                <div key={f.label} className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">{f.label}</p>
                  <p className="mt-1 text-sm text-slate-200">{f.value}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Profile intelligence extracted from platform metadata.</p>
          )}

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Platform Contributions</h4>
            <div className="space-y-2">
              {verifiedPlatforms.map((pp) => (
                <div key={pp.entityId} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm text-cyan-300">{pp.platformLabel || pp.platform}</span>
                    <Badge variant={pp.verified ? 'success' : 'muted'}>{pp.verified ? 'Verified' : 'Unverified'}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {pp.displayName || pp.handle}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-600">
                    {pp.sources.join(', ')} · {pp.fieldCount} extracted field(s)
                  </p>
                </div>
              ))}
            </div>
          </div>

          {isIdentity && (
            <div className="grid gap-4 sm:grid-cols-2">
              <ProvenanceList label="Emails" items={identity.emails.filter(isDisplayableEmailField)} />
              <ProvenanceList label="Usernames" items={identity.usernames} />
              <ProvenanceList label="Websites" items={identity.websites} />
              <ProvenanceList label="Organizations" items={identity.organizations} />
            </div>
          )}
        </div>

        {(isIdentity ? identity.primary_avatar : (profile as { primary_avatar?: string }).primary_avatar) && (
          <div className="flex justify-center lg:justify-end">
            <img
              src={(isIdentity ? identity.primary_avatar : (profile as { primary_avatar?: string }).primary_avatar)!}
              alt="Profile"
              className="h-40 w-40 rounded-xl border border-slate-700 object-cover"
            />
          </div>
        )}
      </div>
    </div>
  );
}
