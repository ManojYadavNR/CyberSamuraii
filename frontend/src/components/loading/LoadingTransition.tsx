import type { ReactNode } from 'react';
import { Spinner } from './Spinner';
import { useSmoothLoading } from './useSmoothLoading';

type LoadingTransitionProps = {
  loading: boolean;
  fallback: ReactNode;
  children: ReactNode;
  minMs?: number;
  className?: string;
  /** When true, dims existing content and shows a centered spinner (refetch UX). */
  overlay?: boolean;
  overlayLabel?: string;
};

export function LoadingTransition({
  loading,
  fallback,
  children,
  minMs,
  className = '',
  overlay = false,
  overlayLabel,
}: LoadingTransitionProps) {
  const { showFallback, showContent, contentVisible, exiting } = useSmoothLoading(loading, minMs);

  if (overlay) {
    return (
      <div className={`relative min-h-[10rem] ${className}`}>
        <div className={`smooth-content-reveal ${!loading ? 'smooth-content-reveal--visible' : ''}`}>
          {children}
        </div>
        <div
          className={`loading-overlay ${loading ? 'loading-overlay--visible' : ''}`}
          aria-busy={loading}
          aria-hidden={!loading}
        >
          <Spinner size="lg" variant="ring" />
          {overlayLabel ? <p className="loading-overlay__label">{overlayLabel}</p> : null}
        </div>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      {showFallback && (
        <div
          className={`smooth-load-fallback ${exiting ? 'smooth-load-fallback--exit' : ''}`}
          aria-busy={!exiting}
          aria-hidden={exiting}
        >
          {fallback}
        </div>
      )}
      {showContent && (
        <div
          className={`smooth-load-content ${contentVisible ? 'smooth-load-content--visible' : 'smooth-load-content--entering'}`}
        >
          {children}
        </div>
      )}
    </div>
  );
}
