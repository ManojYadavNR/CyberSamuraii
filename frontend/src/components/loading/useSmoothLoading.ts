import { useEffect, useRef, useState } from 'react';

const DEFAULT_MIN_MS = 520;
const FADE_MS = 480;

export type LoadingPhase = 'loading' | 'exiting' | 'ready';

/** Keeps loader visible for a minimum time, then crossfades to content. */
export function useSmoothLoading(loading: boolean, minMs = DEFAULT_MIN_MS) {
  const [phase, setPhase] = useState<LoadingPhase>(loading ? 'loading' : 'ready');
  const startedAt = useRef(Date.now());
  const timers = useRef<number[]>([]);

  useEffect(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];

    if (loading) {
      startedAt.current = Date.now();
      setPhase('loading');
      return;
    }

    const elapsed = Date.now() - startedAt.current;
    const wait = Math.max(0, minMs - elapsed);

    const enterTimer = window.setTimeout(() => {
      setPhase('exiting');
      const readyTimer = window.setTimeout(() => setPhase('ready'), FADE_MS);
      timers.current.push(readyTimer);
    }, wait);
    timers.current.push(enterTimer);

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [loading, minMs]);

  return {
    phase,
    showFallback: phase === 'loading' || phase === 'exiting',
    showContent: phase === 'exiting' || phase === 'ready',
    contentVisible: phase === 'ready',
    exiting: phase === 'exiting',
  };
}
