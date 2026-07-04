import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AnimatedBackground } from './AnimatedBackground';
import { AnimatedLogo } from './AnimatedLogo';

interface StartupIntroProps {
  onComplete: () => void;
}

export function StartupIntro({ onComplete }: StartupIntroProps) {
  useEffect(() => {
    // Total animation time is roughly:
    // Logo finishes rotation at ~3.0s
    // Text fades in over 0.6s (finishes around 3.6s)
    // Loading bar animates over 1.2s (finishes around 4.8s)
    // Extra slight delay before exit
    const timer = setTimeout(() => {
      onComplete();
    }, 5500);
    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <AnimatePresence>
      <motion.div 
        className="fixed inset-0 z-[99999] flex flex-col items-center justify-center overflow-hidden bg-[#070b14] text-slate-100 font-sans"
        exit={{ opacity: 0, scale: 1.03 }}
        transition={{ duration: 0.7, ease: 'easeInOut' }}
        style={{ willChange: 'transform, opacity' }}
      >
        <AnimatedBackground />

        {/* Camera Zoom Container */}
        <motion.div
          className="relative z-10 flex flex-col items-center justify-center"
          initial={{ scale: 1 }}
          animate={{ scale: 1.08 }}
          transition={{ duration: 1, ease: 'linear' }}
          style={{ willChange: 'transform' }}
        >
          <AnimatedLogo />

          {/* Text Container */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2.0, duration: 0.4, ease: 'easeOut' }}
            className="mt-8 flex flex-col items-center justify-center"
            style={{ willChange: 'opacity' }}
          >
            <h1 className="text-xl font-bold tracking-widest text-slate-100 sm:text-2xl md:text-3xl">
              CID Intelligence Platform
            </h1>
            <p className="mt-2 text-xs uppercase tracking-[0.3em] text-cyan-500/80 sm:text-sm">
              Powered by CyberSamurai
            </p>

            {/* Loading Bar */}
            <div className="mt-6 h-[2px] w-[220px] overflow-hidden rounded-full bg-slate-800/60">
              <motion.div
                initial={{ x: '-100%' }}
                animate={{ x: '0%' }}
                transition={{ delay: 2.5, duration: 0.8, ease: 'easeInOut' }}
                className="h-full w-full rounded-full"
                style={{ 
                  background: 'linear-gradient(90deg, rgba(6,182,212,0.1) 0%, rgba(6,182,212,1) 50%, rgba(59,130,246,1) 100%)',
                  willChange: 'transform'
                }}
              />
            </div>
          </motion.div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
