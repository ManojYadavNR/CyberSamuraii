import { useEffect, useRef } from 'react';

const CircuitPattern = () => (
  <svg 
    className="absolute inset-0 h-full w-full opacity-[0.25] mix-blend-screen"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs>
      <pattern id="circuit-pattern" width="100" height="100" patternUnits="userSpaceOnUse">
        <g fill="none" stroke="#38bdf8" strokeWidth="0.5" strokeOpacity="0.4">
          <path d="M0 20 l20 0 l10 10 l40 0 l10 -10 l20 0" />
          <path d="M0 40 l15 0 l10 10 l50 0 l10 -10 l15 0" />
          <path d="M0 60 l25 0 l10 10 l30 0 l10 -10 l25 0" />
          <path d="M0 80 l35 0 l10 10 l10 0 l10 -10 l35 0" />
          <path d="M20 0 l0 15 l10 10 l0 50 l10 10 l0 15" />
          <path d="M40 0 l0 25 l10 10 l0 30 l10 10 l0 25" />
          <path d="M60 0 l0 35 l10 10 l0 10 l10 10 l0 35" />
          <path d="M80 0 l0 5 l10 10 l0 70 l10 10 l0 5" />
        </g>
        <g fill="#38bdf8" fillOpacity="0.8">
          <circle cx="30" cy="30" r="1.5">
            <animate attributeName="r" values="1.5;3;1.5" dur="3s" repeatCount="indefinite" />
            <animate attributeName="fill-opacity" values="0.8;1;0.8" dur="3s" repeatCount="indefinite" />
          </circle>
          <circle cx="70" cy="30" r="1.5">
            <animate attributeName="r" values="1.5;3;1.5" dur="4s" repeatCount="indefinite" />
            <animate attributeName="fill-opacity" values="0.8;1;0.8" dur="4s" repeatCount="indefinite" />
          </circle>
          <circle cx="30" cy="70" r="1.5">
            <animate attributeName="r" values="1.5;3;1.5" dur="2s" repeatCount="indefinite" />
            <animate attributeName="fill-opacity" values="0.8;1;0.8" dur="2s" repeatCount="indefinite" />
          </circle>
          <circle cx="70" cy="70" r="1.5">
            <animate attributeName="r" values="1.5;3;1.5" dur="5s" repeatCount="indefinite" />
            <animate attributeName="fill-opacity" values="0.8;1;0.8" dur="5s" repeatCount="indefinite" />
          </circle>
          <circle cx="50" cy="50" r="2">
            <animate attributeName="r" values="2;4;2" dur="3.5s" repeatCount="indefinite" />
            <animate attributeName="fill-opacity" values="0.8;1;0.8" dur="3.5s" repeatCount="indefinite" />
          </circle>
        </g>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#circuit-pattern)" />
  </svg>
);

export function GridOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    const fontSize = 14;
    const columns = Math.floor(width / fontSize);
    const drops: number[] = Array(columns).fill(0).map(() => Math.random() * -100);

    let animationFrameId: number;

    const draw = () => {
      ctx.fillStyle = 'rgba(2, 6, 23, 0.1)';
      ctx.fillRect(0, 0, width, height);

      ctx.font = `${fontSize}px monospace`;
      
      for (let i = 0; i < drops.length; i++) {
        const isCyan = Math.random() > 0.5;
        ctx.fillStyle = isCyan ? 'rgba(56, 189, 248, 0.4)' : 'rgba(16, 185, 129, 0.4)'; 
        
        const text = chars[Math.floor(Math.random() * chars.length)];
        const x = i * fontSize;
        const y = drops[i] * fontSize;

        ctx.fillText(text, x, y);

        if (y > height && Math.random() > 0.99) {
          drops[i] = 0;
        }
        drops[i] += 0.5;
      }

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden bg-slate-950">
      
      {/* Base Gradient Layer */}
      <div className="absolute inset-0 bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950" />

      {/* Circuit Board Pattern */}
      <CircuitPattern />
      
      {/* Matrix Digital Rain Canvas */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full opacity-50 mix-blend-screen" />
      
      {/* Elegant Dot Grid */}
      <div 
        className="absolute inset-0 opacity-30 mix-blend-overlay"
        style={{
          backgroundImage: `radial-gradient(circle at center, #38bdf8 1px, transparent 1px)`,
          backgroundSize: '24px 24px'
        }}
      />

      {/* Glowing Orbs for Depth */}
      <div className="absolute top-0 left-0 h-full w-full overflow-hidden">
        <div className="absolute -top-[20%] -left-[10%] h-[50%] w-[50%] rounded-full bg-sky-600/10 blur-[120px]" />
        <div className="absolute -bottom-[20%] -right-[10%] h-[50%] w-[50%] rounded-full bg-emerald-600/10 blur-[120px]" />
      </div>

      {/* Dark Vignette to keep text readable and focus center */}
      <div 
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 0%, rgba(2,6,23,0.8) 70%, rgba(2,6,23,1) 100%)'
        }}
      />
      
    </div>
  );
}
