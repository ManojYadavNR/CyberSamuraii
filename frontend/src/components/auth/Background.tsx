import { motion } from 'framer-motion';

export function Background() {
  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" style={{ backgroundColor: '#02040A' }}>
      
      {/* Heavy base gradient to mimic the deep space/navy feel */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(8,16,36,1)_0%,rgba(2,4,10,1)_100%)]" />

      {/* Cyber Grid - extremely subtle */}
      <div 
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `linear-gradient(rgba(255, 255, 255, 1) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 1) 1px, transparent 1px)`,
          backgroundSize: '40px 40px'
        }}
      />
      
      {/* Intense Network Lines & Subtle Map Simulation */}
      <div className="absolute inset-0 opacity-[0.25] mix-blend-screen flex items-center justify-center">
         <svg viewBox="0 0 1200 800" className="w-full h-full object-cover">
            {/* Horizontal & Vertical tech lines */}
            <path d="M0 200 L1200 200 M0 600 L1200 600 M300 0 L300 800 M900 0 L900 800" stroke="#1E3A8A" strokeWidth="0.5" opacity="0.4"/>
            
            {/* Simulated Karnataka Map outline (abstract) */}
            <path d="M400 150 Q 450 100 550 120 T 650 250 T 600 450 T 500 650 T 350 550 Z" fill="none" stroke="#2563EB" strokeWidth="1" opacity="0.3" strokeDasharray="4 4" />
            
            {/* Aesthetic nodes mapping mapping to the outline */}
            <path d="M100 200 L 300 50 L 550 120 L 900 200 L 1100 400" fill="none" stroke="#3B82F6" strokeWidth="0.5" opacity="0.6"/>
            <path d="M50 400 L 250 200 L 450 350 L 600 450 L 850 350 L 1150 600" fill="none" stroke="#3B82F6" strokeWidth="0.5" opacity="0.6"/>
            <path d="M350 550 L 500 650 L 750 700 L 1050 750" fill="none" stroke="#3B82F6" strokeWidth="0.5" opacity="0.6"/>
            
            {/* Glowing Network Nodes */}
            {[...Array(40)].map((_, i) => {
               const cx = Math.random() * 1200;
               const cy = Math.random() * 800;
               return (
                 <g key={i}>
                    {/* Core node */}
                    <circle cx={cx} cy={cy} r="1.5" fill="#60A5FA" opacity="0.9" />
                    {/* Outer glow */}
                    <circle cx={cx} cy={cy} r="4" fill="#60A5FA" opacity="0.3" />
                 </g>
               )
            })}
            
            {/* The giant bright node from reference image 2 */}
            <g transform="translate(600, 450)">
              <circle cx="0" cy="0" r="2" fill="#FFFFFF" />
              <circle cx="0" cy="0" r="15" fill="url(#cyanGlow)" opacity="0.8" />
              <circle cx="0" cy="0" r="50" fill="none" stroke="#3B82F6" strokeWidth="0.5" opacity="0.5" />
              <circle cx="0" cy="0" r="100" fill="none" stroke="#3B82F6" strokeWidth="0.2" opacity="0.3" />
              <line x1="-120" y1="0" x2="120" y2="0" stroke="#3B82F6" strokeWidth="0.5" opacity="0.5" />
              <line x1="0" y1="-120" x2="0" y2="120" stroke="#3B82F6" strokeWidth="0.5" opacity="0.5" />
            </g>
            
            <defs>
              <radialGradient id="cyanGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#22D3EE" stopOpacity="1" />
                <stop offset="100%" stopColor="#22D3EE" stopOpacity="0" />
              </radialGradient>
            </defs>
         </svg>
      </div>
      
      {/* Moving Data Particles */}
      <motion.div 
        className="absolute inset-0 opacity-[0.04]"
        animate={{ backgroundPosition: ['0px 0px', '150px 150px'] }}
        transition={{ repeat: Infinity, duration: 30, ease: "linear" }}
        style={{
          backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)',
          backgroundSize: '30px 30px',
        }}
      />

      {/* Extreme Vignette to darken edges just like the image */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_20%,rgba(0,0,0,0.85)_100%)]" />
    </div>
  );
}
