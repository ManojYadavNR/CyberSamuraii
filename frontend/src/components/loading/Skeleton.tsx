import { Spinner } from './Spinner';

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton-shimmer rounded-md bg-slate-800/80 ${className}`} />;
}

export function SkeletonText({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`} />
      ))}
    </div>
  );
}

export function CardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="intel-panel rounded-xl p-4">
          <Skeleton className="mb-3 h-2 w-24" />
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="intel-panel overflow-hidden rounded-xl p-3">
      <div className="mb-3 flex gap-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-3">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} className="h-8 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="mb-2 h-6 w-56" />
        <Skeleton className="h-4 w-40" />
      </div>
      <CardSkeleton count={6} />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="intel-panel rounded-xl p-4">
          <Skeleton className="mb-4 h-4 w-32" />
          <SkeletonText lines={6} />
        </div>
        <div className="intel-panel rounded-xl p-4">
          <Skeleton className="mb-4 h-4 w-40" />
          <SkeletonText lines={6} />
        </div>
      </div>
    </div>
  );
}

export function PageLoader({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4">
      <Spinner size="lg" variant="ring" />
      <p className="text-sm font-medium tracking-wide text-slate-400">{label}</p>
    </div>
  );
}
