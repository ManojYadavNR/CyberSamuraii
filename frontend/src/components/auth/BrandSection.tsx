import { motion } from 'framer-motion';
import { FeatureCard } from './FeatureCard';
import { LuGlobe, LuActivity, LuUsers, LuNetwork, LuFileText } from 'react-icons/lu';

const features = [
  { title: 'OSINT COLLECTION', icon: LuGlobe },
  { title: 'BEHAVIORAL ANALYTICS', icon: LuActivity },
  { title: 'IDENTITY CORRELATION', icon: LuUsers },
  { title: 'GRAPH INTELLIGENCE', icon: LuNetwork },
  { title: 'EVIDENCE MANAGEMENT', icon: LuFileText },
];

export function BrandSection() {
  return (
    <div className="flex flex-col items-center text-center max-w-4xl mx-auto w-full z-10 mt-8 md:mt-0">
      
      {/* Dynamic Logo/Shield container */}
      <motion.div 
        initial={{ y: 50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="relative mb-6"
      >
        <div className="absolute inset-0 bg-blue-500/10 blur-[60px] rounded-full pointer-events-none" />
        <img 
          src="/ccitr_logo.png" 
          alt="CCITR Logo" 
          className="w-48 h-48 md:w-[260px] md:h-[260px] object-contain relative z-10 drop-shadow-[0_0_30px_rgba(59,130,246,0.3)]"
        />
      </motion.div>
      
      <motion.h1 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.2 }}
        className="text-[36px] md:text-[56px] bg-clip-text text-transparent bg-gradient-to-b from-[#FFFFFF] via-[#E2E8F0] to-[#94A3B8] mb-2 leading-none tracking-wide"
        style={{ 
          fontFamily: "'Michroma', sans-serif",
          textShadow: '0 4px 40px rgba(59,130,246,0.3)' 
        }}
      >
        CYBERSAMURAI
      </motion.h1>
      
      <motion.h2 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
        className="text-sm md:text-[18px] font-bold text-[#94A3B8] tracking-[0.15em] mb-8 uppercase"
      >
        AI-DRIVEN SOCMINT INTELLIGENCE PLATFORM
      </motion.h2>
      
      {/* Star icon above the tagline */}
      <motion.div
         initial={{ scale: 0 }}
         animate={{ scale: 1 }}
         transition={{ duration: 0.5, delay: 0.4 }}
         className="text-[#60A5FA] mb-2 text-xs"
      >
        ★
      </motion.div>
      
      <motion.p 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.5 }}
        className="text-[11px] md:text-[13px] font-bold tracking-[0.3em] text-[#D4AF37] mb-12 drop-shadow-[0_0_10px_rgba(212,175,55,0.4)]"
      >
        INTELLIGENCE. INTEGRITY. IMPACT.
      </motion.p>
      
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 w-full px-4 md:px-0">
        {features.map((feature, idx) => (
          <FeatureCard 
            key={feature.title} 
            title={feature.title} 
            icon={feature.icon} 
            delay={0.6 + idx * 0.1}
          />
        ))}
      </div>
    </div>
  );
}
