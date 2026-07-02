interface IamPageHeaderProps {
  onCreateUser: () => void;
  onExport: () => void;
}

export function IamPageHeader({ onCreateUser, onExport }: IamPageHeaderProps) {
  return (
    <div className="iam-sticky-header">
      <div className="flex flex-col gap-4 pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400/80">Identity & Access Management</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white">Administration</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Manage investigators, agencies, permissions, security, and system configuration.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onCreateUser} className="iam-btn-primary">
            <span aria-hidden>+</span> Create User
          </button>
          <button type="button" className="iam-btn-ghost" title="Import users (coming soon)" disabled>
            Import Users
          </button>
          <button type="button" onClick={onExport} className="iam-btn-ghost">
            Export
          </button>
          <button type="button" className="iam-btn-ghost" title="Settings (coming soon)" disabled>
            Settings
          </button>
        </div>
      </div>
    </div>
  );
}
