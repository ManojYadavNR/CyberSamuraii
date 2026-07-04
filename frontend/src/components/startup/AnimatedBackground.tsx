import { motion } from 'framer-motion';
import { GridOverlay } from './GridOverlay';

export function AnimatedBackground() {
  // Generate random particles
  const particles = Array.from({ length: 40 }).map((_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 2 + 1,
    duration: Math.random() * 20 + 20,
    delay: Math.random() * 5,
  }));

  return (
    <div className="absolute inset-0 z-0 overflow-hidden bg-[#070b14]">
      {/* Soft radial gradient base */}
      <div 
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(6, 182, 212, 0.15), transparent), radial-gradient(ellipse 60% 40% at 100% 100%, rgba(59, 130, 246, 0.1), transparent)',
        }}
      />

      {/* Subtle moving dot grid */}
      <motion.div
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: 'radial-gradient(rgba(148, 163, 184, 0.2) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
        animate={{ y: [0, 40] }}
        transition={{ repeat: Infinity, duration: 10, ease: 'linear' }}
      />

      {/* Animated wave mesh */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.15 }}
        transition={{ duration: 1, delay: 1.2 }}
        className="absolute inset-0 flex items-center justify-center"
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-[200%] w-[200%] max-w-none opacity-20">
          <defs>
            <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
              <path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(6, 182, 212, 0.2)" strokeWidth="0.5" />
            </pattern>
          </defs>
          <motion.rect
            width="100%"
            height="100%"
            fill="url(#grid)"
            animate={{ rotateZ: [0, 5, 0, -5, 0], scale: [1, 1.05, 1, 1.05, 1] }}
            transition={{ repeat: Infinity, duration: 30, ease: 'easeInOut' }}
            style={{ transformOrigin: 'center' }}
          />
        </svg>
      </motion.div>

      {/* Slow floating particles */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 2, delay: 0.5 }}
        className="absolute inset-0"
      >
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute rounded-full bg-cyan-100/20 blur-[1px]"
            style={{
              left: `${p.x}%`,
              top: `${p.y}%`,
              width: p.size,
              height: p.size,
            }}
            animate={{
              y: ['0vh', '-20vh'],
              x: ['0vw', `${Math.random() * 10 - 5}vw`],
              opacity: [0, 0.5, 0],
            }}
            transition={{
              repeat: Infinity,
              duration: p.duration,
              delay: p.delay,
              ease: 'linear',
            }}
          />
        ))}
      </motion.div>

      {/* Premium grid overlay */}
      <GridOverlay />

      {/* Vignette edges */}
      <div className="absolute inset-0 shadow-[inset_0_0_150px_rgba(0,0,0,0.9)]" />

      {/* Slight noise texture */}
      <div 
        className="absolute inset-0 mix-blend-overlay opacity-20 pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}
