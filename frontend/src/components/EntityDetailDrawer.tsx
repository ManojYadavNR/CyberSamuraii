import { useInvestigationStore } from '../store/investigationStore';
import { flattenAccounts } from '../lib/uiHelpers';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';

export function EntityDetailDrawer() {
  const drawerOpen = useInvestigationStore((s) => s.drawerOpen);
  const selectedEntityId = useInvestigationStore((s) => s.selectedEntityId);
  const result = useInvestigationStore((s) => s.result);
  const closeDrawer = useInvestigationStore((s) => s.closeDrawer);

  if (!drawerOpen || !selectedEntityId || !result) return null;

  const entity = flattenAccounts(result).find((a) => a.id === selectedEntityId);
  if (!entity) return null;

  const cluster = entity.cluster;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={closeDrawer} />
      <aside className="drawer-enter fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-slate-800 bg-[#0a0f1a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-500">Entity Detail</p>
            <h3 className="font-mono text-lg text-white">{entity.platform}</h3>
          </div>
          <button onClick={closeDrawer} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white">✕</button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Account Details</h4>
            <div className="intel-card space-y-2 p-4 text-sm">
              {entity.displayName && <Row label="Name" value={entity.displayName} />}
              <Row label="Handle" value={entity.handle} mono />
              <Row label="Platform" value={entity.platform} />
              {entity.bio && <Row label="Bio" value={entity.bio} />}
              {entity.location && <Row label="Location" value={entity.location} />}
              {entity.website && <Row label="Website" value={entity.website} mono />}
              {entity.email && <Row label="Email" value={entity.email} mono />}
              {entity.organizations && entity.organizations.length > 0 && (
                <Row label="Organization" value={entity.organizations.join(', ')} />
              )}
              {entity.url && <Row label="URL" value={entity.url} mono link />}
              <Row label="Cluster" value={entity.clusterId} mono />
            </div>
          </section>

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Confidence</h4>
            <div className="intel-card p-4">
              <div className="mb-2 flex justify-between text-sm">
                <span className="text-slate-400">Link confidence</span>
                <span className="font-bold text-white">{entity.confidence.toFixed(1)}%</span>
              </div>
              <ConfidenceBar score={entity.confidence} />
              <div className="mt-3 flex gap-2">
                <Badge variant={entity.verified ? 'success' : 'muted'}>{entity.verified ? 'Verified' : 'Unverified'}</Badge>
                <Badge variant="info">{entity.evidenceCount} signals</Badge>
              </div>
            </div>
          </section>

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Source Tools</h4>
            <div className="flex flex-wrap gap-1.5">
              {(entity.sources.length ? entity.sources : ['unknown']).map((s) => (
                <Badge key={s} variant="muted">{s}</Badge>
              ))}
            </div>
          </section>

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Correlation Signals</h4>
            <div className="space-y-2">
              {cluster.evidence.map((ev) => (
                <div key={ev.type} className="intel-card flex items-center justify-between p-3 text-sm">
                  <span className="capitalize text-slate-400">{ev.type}</span>
                  <span className="font-mono text-slate-200">{(ev.score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Explainability</h4>
            <ul className="space-y-2">
              {cluster.explainability.slice(0, 8).map((line, i) => (
                <li key={i} className="rounded-lg border-l-2 border-cyan-500/50 bg-slate-800/40 px-3 py-2 text-xs leading-relaxed text-slate-300">
                  {line}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Associated Accounts</h4>
            <div className="flex flex-wrap gap-1">
              {cluster.linked_account_refs.filter((r) => r !== `${entity.platform.split('.')[0]}:${entity.handle}`).slice(0, 12).map((ref) => (
                <Badge key={ref} variant="default">{ref}</Badge>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}

function Row({ label, value, mono, link }: { label: string; value: string; mono?: boolean; link?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-slate-500">{label}</span>
      {link ? (
        <a href={value.startsWith('http') ? value : `https://${value}`} target="_blank" rel="noreferrer" className="truncate text-cyan-400 hover:underline">
          {value}
        </a>
      ) : (
        <span className={`truncate text-right text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
      )}
    </div>
  );
}
