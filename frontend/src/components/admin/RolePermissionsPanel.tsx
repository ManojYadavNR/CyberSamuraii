import { useEffect, useMemo, useState } from 'react';
import type { IamUser } from './iamTypes';
import {
  caseRelationshipOptions,
  getRolePermissions,
  loadRbacConfig,
  matrixPermissions,
  organizationalRankOptions,
  permissionLabel,
} from '../../lib/permissions';

interface RolePermissionsPanelProps {
  users: IamUser[];
  onCreateUser: () => void;
}

export function RolePermissionsPanel({ users, onCreateUser }: RolePermissionsPanelProps) {
  const [selectedRank, setSelectedRank] = useState('PSI');
  const [selectedRelationship, setSelectedRelationship] = useState('assistant_investigator');
  const [configLoaded, setConfigLoaded] = useState(false);

  useEffect(() => {
    loadRbacConfig().finally(() => setConfigLoaded(true));
  }, []);

  const rankCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    users.forEach((u) => {
      const rank = u.rank_code || u.role;
      counts[rank] = (counts[rank] || 0) + 1;
    });
    return counts;
  }, [users]);

  const ranks = organizationalRankOptions();
  const globalPermissions = getRolePermissions(selectedRank);
  const casePermissions = matrixPermissions(selectedRank, selectedRelationship);
  const relationships = caseRelationshipOptions();

  return (
    <div className="iam-card">
      <h3 className="text-sm font-semibold text-white">Organizational ranks & permission matrix</h3>
      <p className="mt-1 text-xs text-slate-500">
        Permissions depend on organizational rank × case relationship. Customize hierarchy in{' '}
        <code className="text-cyan-400">config/rbac.json</code>.
      </p>

      <div className="mt-4 rounded-lg border border-cyan-500/20 bg-cyan-950/20 px-3 py-2.5 text-xs text-cyan-100">
        <strong>Provision users:</strong>{' '}
        <button type="button" onClick={onCreateUser} className="font-semibold text-cyan-300 underline">
          Create User
        </button>{' '}
        — set rank, department, supervisor. Assign case relationships when building investigation teams.
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="iam-field-label">Organizational rank</p>
          <div className="flex flex-wrap gap-2">
            {ranks.map((rank) => (
              <button
                key={rank.code}
                type="button"
                onClick={() => setSelectedRank(rank.code)}
                className={`rounded-full border px-2.5 py-1 text-[10px] transition ${
                  selectedRank === rank.code
                    ? 'border-cyan-500/50 bg-cyan-950/40 text-cyan-200'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                {rank.code} · {rankCounts[rank.code] || 0}
              </button>
            ))}
          </div>
        </div>
        <div>
          <p className="iam-field-label">Case relationship (matrix column)</p>
          <div className="flex flex-wrap gap-2">
            {relationships.map((rel) => (
              <button
                key={rel.code}
                type="button"
                onClick={() => setSelectedRelationship(rel.code)}
                className={`rounded-full border px-2.5 py-1 text-[10px] transition ${
                  selectedRelationship === rel.code
                    ? 'border-amber-500/50 bg-amber-950/30 text-amber-200'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                {rel.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="iam-field-label">Global permissions ({selectedRank})</p>
          <div className="flex flex-wrap gap-2">
            {globalPermissions.map((perm) => (
              <span key={perm} className="iam-badge-soft text-cyan-100/90">{permissionLabel(perm)}</span>
            ))}
          </div>
        </div>
        <div>
          <p className="iam-field-label">
            Case permissions ({selectedRank} × {relationships.find((r) => r.code === selectedRelationship)?.label})
          </p>
          <div className="flex flex-wrap gap-2">
            {!configLoaded ? (
              <span className="text-xs text-slate-500">Loading matrix…</span>
            ) : casePermissions.length === 0 ? (
              <span className="text-xs text-slate-500">No case permissions for this combination.</span>
            ) : casePermissions.map((perm) => (
              <span key={perm} className="iam-badge-soft text-amber-100/90">{permissionLabel(perm)}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
