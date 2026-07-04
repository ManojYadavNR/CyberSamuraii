import React from 'react';

interface SecurityBadgeProps {
  icon: React.ElementType;
  title: string;
}

export function SecurityBadge({ icon: Icon, title }: SecurityBadgeProps) {
  return (
    <div className="flex flex-col items-center text-center group w-1/3">
      <div className="w-10 h-10 rounded-full border border-slate-600/50 flex items-center justify-center mb-2 bg-[#0A101C] group-hover:border-[#3B82F6] group-hover:bg-[#3B82F6]/10 transition-all duration-300 shadow-[0_4px_10px_rgba(0,0,0,0.2)]">
        <Icon className="w-[18px] h-[18px] text-[#60A5FA] group-hover:text-[#93C5FD]" strokeWidth={1.5} />
      </div>
      <span className="text-[8px] font-bold text-[#94A3B8] uppercase tracking-[0.1em] group-hover:text-[#E2E8F0] transition-colors w-full leading-[1.4]">
        {title.split(' ').map((word, i) => (
          <React.Fragment key={i}>
            {word}
            {i !== title.split(' ').length - 1 && <br />}
          </React.Fragment>
        ))}
      </span>
    </div>
  );
}
