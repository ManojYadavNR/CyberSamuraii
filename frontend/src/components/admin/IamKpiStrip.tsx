export interface IamKpi {
  id: string;
  icon: string;
  label: string;
  value: string | number;
  description: string;
  trend?: string;
}

export function IamKpiStrip({ kpis, loading }: { kpis: IamKpi[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="iam-kpi-grid">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="iam-kpi-card skeleton-shimmer" style={{ minHeight: 120, animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
    );
  }

  return (
    <div className="iam-kpi-grid stagger-fade-in">
      {kpis.map((kpi, i) => (
        <div key={kpi.id} className="iam-kpi-card" style={{ animationDelay: `${i * 50}ms` }}>
          {kpi.trend && <span className="iam-kpi-trend">{kpi.trend}</span>}
          <div className="iam-kpi-icon">{kpi.icon}</div>
          <div className="iam-kpi-value">{kpi.value}</div>
          <div className="iam-kpi-label">{kpi.label}</div>
          <div className="iam-kpi-desc">{kpi.description}</div>
        </div>
      ))}
    </div>
  );
}
