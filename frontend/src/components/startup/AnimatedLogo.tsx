import { motion, useReducedMotion } from 'framer-motion';
import type { Variants } from 'framer-motion';

export function AnimatedLogo() {
  const prefersReducedMotion = useReducedMotion();

  // If prefers-reduced-motion is enabled, skip the 3D rotation
  const variants: Variants = prefersReducedMotion 
    ? {
        initial: { opacity: 0, scale: 0.72 },
        animate: { 
          opacity: 1, 
          scale: 1,
          transition: { delay: 0.2, duration: 1, ease: [0.22, 1, 0.36, 1] } 
        }
      }
    : {
        initial: { 
          opacity: 0, 
          scale: 0.72, 
          rotateY: -180, 
          rotateX: 10 
        },
        animate: {
          opacity: 1,
          scale: 1,
          rotateY: 0,
          rotateX: 0,
          transition: {
            rotateY: { delay: 0.05, duration: 0.3, ease: [0.22, 1, 0.36, 1] },
            rotateX: { delay: 0.05, duration: 0.3, ease: [0.22, 1, 0.36, 1] },
            scale: { delay: 0.05, duration: 0.25, ease: [0.22, 1, 0.36, 1] },
            opacity: { delay: 0.05, duration: 0.2, ease: 'easeOut' },
          }
        }
      };

  return (
    <div className="relative z-10 flex flex-col items-center justify-center">
      {/* Radial glow behind logo */}
      <motion.div
        initial={{ opacity: 0, scale: 0.5 }}
        animate={{ opacity: [0, 0.8, 0.4], scale: 1 }}
        transition={{ delay: 0.3, duration: 3, ease: 'easeInOut' }}
        className="absolute h-64 w-64 rounded-full bg-cyan-600/20 blur-[60px]"
        style={{ willChange: 'opacity, transform' }}
      />
      
      {/* Perspective wrapper for 3D rotation */}
      <div style={{ perspective: '1200px' }}>
        <motion.div
          variants={variants}
          initial="initial"
          animate="animate"
          className="relative flex items-center justify-center"
          style={{ 
            transformStyle: 'preserve-3d',
            willChange: 'transform, opacity'
          }}
        >
          {/* Logo with drop shadow and soft bloom */}
          <img 
            src="/cid_logo.png" 
            alt="CID Logo" 
            className="w-[180px] drop-shadow-[0_10px_25px_rgba(6,182,212,0.3)] md:w-[220px] lg:w-[260px]"
            style={{ 
              filter: 'drop-shadow(0 0 15px rgba(6, 182, 212, 0.25)) drop-shadow(0 20px 30px rgba(0, 0, 0, 0.8))' 
            }}
          />
        </motion.div>
      </div>
    </div>
  );
}
