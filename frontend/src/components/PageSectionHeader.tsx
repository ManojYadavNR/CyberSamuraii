import type { ReactNode } from 'react';
import type { IconType } from 'react-icons';

export interface PageSectionHeaderProps {
  title: string;
  subtitle?: string;
  count?: number | string;
  compact?: boolean;
  icon: IconType;
  actions?: ReactNode;
}

export function PageSectionHeader({
  title,
  subtitle,
  count,
  compact = false,
  icon: Icon,
  actions,
}: PageSectionHeaderProps) {
  return (
    <div className={`page-head ${compact ? 'page-head--compact' : ''}`}>
      <div className="page-head__banner">
        <div className="page-head__full">
          <div className="page-head__icon-wrap" aria-hidden>
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1 className="page-head__title">{title}</h1>
            {subtitle ? <p className="page-head__subtitle">{subtitle}</p> : null}
          </div>
        </div>
        <div className="page-head__compact">
          <Icon className="h-3.5 w-3.5 shrink-0 text-cyan-400" aria-hidden />
          <span className="page-head__compact-title">{title}</span>
          {count !== undefined ? <span className="page-head__compact-count">{count}</span> : null}
        </div>
      </div>
      {actions ? <div className="page-head__actions">{actions}</div> : null}
    </div>
  );
}
