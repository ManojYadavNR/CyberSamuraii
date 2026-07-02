import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Spinner } from './Spinner';

type PageTransitionProps = {
  pageKey: string;
  children: ReactNode;
  contained?: boolean;
};

/** Soft fade between sidebar navigation pages. */
export function PageTransition({ pageKey, children, contained = false }: PageTransitionProps) {
  const [visible, setVisible] = useState(true);
  const [content, setContent] = useState(children);
  const prevKey = useRef(pageKey);
  const childRef = useRef(children);
  const isFirst = useRef(true);
  childRef.current = children;

  useEffect(() => {
    if (isFirst.current) {
      isFirst.current = false;
      setContent(childRef.current);
      return;
    }
    if (pageKey === prevKey.current) {
      setContent(childRef.current);
      return;
    }
    prevKey.current = pageKey;
    setVisible(false);
    const swap = window.setTimeout(() => {
      setContent(childRef.current);
      requestAnimationFrame(() => setVisible(true));
    }, 220);
    return () => clearTimeout(swap);
  }, [pageKey]);

  return (
    <div className={`page-transition ${contained ? 'page-transition--contained' : ''} ${visible ? 'page-transition--visible' : 'page-transition--hidden'}`}>
      {!visible && (
        <div className="page-transition__spinner">
          <Spinner size="lg" variant="ring" />
        </div>
      )}
      <div className={`page-transition__content ${contained ? 'page-transition__content--contained' : ''} ${visible ? '' : 'pointer-events-none opacity-0'}`}>{content}</div>
    </div>
  );
}
