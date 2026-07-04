import { useState, useEffect } from 'react';

export function useStartup() {
  const [isFinished, setIsFinished] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);

  useEffect(() => {
    // Only run the startup intro once per session/reload.
    // In a real app, you might check localStorage or sessionStorage,
    // but for this implementation, we just use a simple state to ensure it runs on mount.
    const hasSeenIntro = sessionStorage.getItem('hasSeenStartupIntro');
    
    if (hasSeenIntro) {
      setIsFinished(true);
      setHasStarted(true);
    } else {
      setHasStarted(true);
    }
  }, []);

  const finishStartup = () => {
    setIsFinished(true);
    sessionStorage.setItem('hasSeenStartupIntro', 'true');
  };

  return {
    isFinished,
    hasStarted,
    finishStartup,
  };
}
