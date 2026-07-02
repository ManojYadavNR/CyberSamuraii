import { useEffect, useRef, useState } from 'react';

export function useCompactPageHeader(resetDeps: unknown[] = []) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [headerCompact, setHeaderCompact] = useState(false);

  useEffect(() => {
    setHeaderCompact(false);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, resetDeps);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setHeaderCompact(el.scrollTop > 24);
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, resetDeps);

  return { scrollRef, headerCompact };
}
