import React from 'react';
import { motion } from 'framer-motion';

interface FeatureCardProps {
  title: string;
  icon: React.ElementType;
  delay: number;
}

export function FeatureCard({ title, icon: Icon, delay }: FeatureCardProps) {
  return (
    <motion.div
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, delay }}
      className="group relative flex flex-col items-center justify-center p-4 rounded-xl border transition-all duration-300 hover:-translate-y-1 overflow-hidden h-[110px]"
      style={{
        background: 'linear-gradient(180deg, rgba(11,18,32,0.6) 0%, rgba(5,8,20,0.8) 100%)',
        borderColor: 'rgba(59,130,246,0.25)',
        boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05), 0 4px 20px rgba(0,0,0,0.3)'
      }}
    >
      {/* Hover glow effects */}
      <div className="absolute inset-0 bg-blue-500/0 group-hover:bg-blue-500/10 transition-colors duration-300" />
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.2)_0%,transparent_70%)]" />
      
      {/* Sharp top edge highlight on hover */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      
      <Icon className="w-8 h-8 text-[#3B82F6] group-hover:text-[#60A5FA] transition-colors duration-300 mb-3 relative z-10 drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]" strokeWidth={1.5} />
      
      <span className="text-[10px] font-bold text-slate-300 group-hover:text-white transition-colors text-center uppercase tracking-[0.1em] relative z-10 leading-[1.2]">
        {title.split(' ').map((word, i) => (
          <React.Fragment key={i}>
            {word}
            {i !== title.split(' ').length - 1 && <br />}
          </React.Fragment>
        ))}
      </span>
    </motion.div>
  );
}
