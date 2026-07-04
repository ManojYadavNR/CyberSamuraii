import { useState, useEffect } from 'react';
import { LuLock, LuClock, LuMapPin, LuShieldCheck } from 'react-icons/lu';

export function StatusBar() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (d: Date) => d.toLocaleTimeString('en-US', { hour12: false }) + ' IST';
  const formatDate = (d: Date) => d.toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' }).toUpperCase();

  return (
    <div className="fixed bottom-0 left-0 right-0 h-[72px] bg-[#050814]/90 backdrop-blur-2xl border-t border-[#508cff]/20 z-50 flex items-center px-8 text-xs justify-between hidden md:flex shadow-[0_-10px_40px_rgba(0,0,0,0.5)]">
      
      <div className="flex items-center space-x-4 flex-1">
        <LuLock className="w-5 h-5 text-slate-500" />
        <div>
          <div className="text-slate-300 font-semibold tracking-wide text-xs mb-0.5">AUTHORIZED PERSONNEL ONLY</div>
          <div className="text-slate-500 text-[10px] tracking-widest uppercase">Unauthorized access is strictly prohibited</div>
        </div>
      </div>
      
      <div className="flex items-center justify-center space-x-4 flex-1 border-l border-slate-800 h-10">
        <LuClock className="w-5 h-5 text-slate-500" />
        <div>
          <div className="text-slate-300 font-semibold tracking-widest text-xs mb-0.5">{formatTime(time)}</div>
          <div className="text-slate-500 text-[10px] tracking-widest uppercase">{formatDate(time)}</div>
        </div>
      </div>

      <div className="flex items-center justify-center space-x-4 flex-1 border-l border-slate-800 h-10">
        <LuMapPin className="w-5 h-5 text-slate-500" />
        <div>
          <div className="text-slate-300 font-semibold tracking-wide text-xs mb-0.5">BENGALURU</div>
          <div className="text-slate-500 text-[10px] tracking-widest uppercase">Karnataka, India</div>
        </div>
      </div>

      <div className="flex items-center justify-end space-x-4 flex-1 border-l border-slate-800 h-10">
        <LuShieldCheck className="w-5 h-5 text-[#508cff]/70" />
        <div className="text-right">
          <div className="text-slate-300 font-semibold tracking-wide text-xs mb-0.5">SECURE NETWORK</div>
          <div className="text-slate-500 text-[10px] tracking-widest uppercase">Encrypted Connection</div>
        </div>
      </div>

    </div>
  );
}
