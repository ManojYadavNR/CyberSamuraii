import type { IamUser } from './iamTypes';

interface OrganizationPanelProps {
  agencies: { id: string; name: string; code?: string }[];
  users: IamUser[];
}

function StatCard({ title, value, desc, icon }: { title: string; value: string | number; desc: string; icon: string }) {
  return (
    <div className="iam-card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{title}</p>
          <p className="mt-1 text-2xl font-bold text-white">{value}</p>
          <p className="mt-1 text-xs text-slate-500">{desc}</p>
        </div>
        <span className="text-2xl opacity-70">{icon}</span>
      </div>
    </div>
  );
}

export function OrganizationPanel({ agencies, users }: OrganizationPanelProps) {
  const departments = new Set(users.map((u) => u.department).filter(Boolean));

  return (
    <div className="iam-card-grid">
      <StatCard title="Agencies" value={agencies.length || 1} desc="Registered law enforcement agencies" icon="🏛️" />
      <StatCard title="Departments" value={departments.size || 1} desc="Operational units across CID" icon="🏬" />
      <StatCard title="Districts" value="—" desc="Jurisdiction mapping (configure in system)" icon="🗺️" />
      <StatCard title="Jurisdictions" value="—" desc="Cross-border coordination zones" icon="⚖️" />
      {agencies.length > 0 && (
        <div className="iam-card col-span-full">
          <h3 className="mb-3 text-sm font-semibold text-white">Registered Agencies</h3>
          <div className="flex flex-wrap gap-2">
            {agencies.map((a) => (
              <span key={a.id} className="rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300">
                {a.name}{a.code ? ` (${a.code})` : ''}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface PlaceholderCardsProps {
  items: { title: string; desc: string; icon: string; status?: string }[];
}

export function PlaceholderCards({ items }: PlaceholderCardsProps) {
  return (
    <div className="iam-card-grid">
      {items.map((item) => (
        <div key={item.title} className="iam-card">
          <div className="flex items-start gap-3">
            <span className="text-2xl">{item.icon}</span>
            <div>
              <h3 className="text-sm font-semibold text-white">{item.title}</h3>
              <p className="mt-1 text-xs text-slate-500">{item.desc}</p>
              {item.status && (
                <span className="mt-2 inline-block rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{item.status}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
