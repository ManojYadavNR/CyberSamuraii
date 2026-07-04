import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { LuShield, LuUser, LuLock, LuEye, LuEyeOff, LuArrowRight, LuFingerprint, LuFileCheck } from 'react-icons/lu';
import { SecurityBadge } from './SecurityBadge';

interface LoginCardProps {
  onSubmit: (e: React.FormEvent, email: string, pass: string) => void;
  onForgotPassword: () => void;
  loading: boolean;
  error: string | null;
}

export function LoginCard({ onSubmit, onForgotPassword, loading, error }: LoginCardProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  return (
    <motion.div 
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className="w-full max-w-[500px] rounded-3xl relative overflow-visible z-10"
    >
      {/* Premium Outer Glow & Border wrapper */}
      <div className="absolute inset-0 rounded-3xl bg-gradient-to-b from-cyan-400/30 to-blue-600/0 p-[1px] shadow-[0_0_80px_rgba(59,130,246,0.15)] pointer-events-none">
         <div className="absolute inset-0 rounded-3xl bg-[#070C16]/95 backdrop-blur-3xl pointer-events-auto shadow-inner" />
      </div>

      {/* Top right intense cyan glow from the reference image */}
      <div className="absolute -top-[1px] right-8 w-48 h-[2px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent blur-[1px]" />
      <div className="absolute -top-10 right-0 w-32 h-32 bg-cyan-400/20 blur-[60px] rounded-full pointer-events-none" />

      {/* Actual Card Content */}
      <div className="relative p-10 pt-12 rounded-3xl overflow-hidden flex flex-col h-full z-10 pointer-events-auto">
        
        {/* Header */}
        <div className="flex flex-col items-center mb-8 relative z-10">
          <div className="w-12 h-12 border border-slate-600/60 rounded-xl flex items-center justify-center bg-[#0B1220] shadow-[0_0_15px_rgba(0,0,0,0.5)] mb-5">
             <div className="flex items-center justify-center border border-slate-400/50 w-7 h-7 rounded p-1">
                <span className="text-white text-[9px] font-bold">CID</span>
             </div>
          </div>
          <h3 className="text-[10px] font-bold tracking-[0.25em] text-slate-300 mb-2 uppercase">WELCOME BACK</h3>
          <h2 className="text-[28px] font-black bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-blue-400 to-cyan-300 tracking-wide mb-3">
            INVESTIGATOR
          </h2>
          <div className="w-full flex items-center justify-center space-x-3 mb-2 opacity-60">
              <div className="h-[1px] bg-gradient-to-r from-transparent to-slate-500 w-16" />
              <p className="text-xs text-slate-300">Please sign in to continue</p>
              <div className="h-[1px] bg-gradient-to-l from-transparent to-slate-500 w-16" />
          </div>
        </div>

        <form onSubmit={(e) => onSubmit(e, email, password)} className="space-y-4 relative z-10">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm text-center">
              {error}
            </div>
          )}
          
          {/* Email Input */}
          <div className="relative group">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <LuUser className="h-5 w-5 text-slate-400 group-focus-within:text-blue-400 transition-colors" strokeWidth={1.5} />
            </div>
            <input
              type="text"
              placeholder="Email Address"
              className="w-full h-[56px] rounded-xl border border-slate-700/80 bg-[#0A101C] pl-[48px] pr-4 text-white text-[13px] placeholder-slate-500 focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] focus:outline-none transition-all shadow-inner"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          {/* Password Input */}
          <div className="relative group">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <LuLock className="h-5 w-5 text-slate-400 group-focus-within:text-blue-400 transition-colors" strokeWidth={1.5} />
            </div>
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              className="w-full h-[56px] rounded-xl border border-slate-700/80 bg-[#0A101C] pl-[48px] pr-12 text-white text-[13px] placeholder-slate-500 focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] focus:outline-none transition-all shadow-inner"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-500 hover:text-slate-300 transition-colors"
            >
              {showPassword ? <LuEyeOff className="h-5 w-5" strokeWidth={1.5} /> : <LuEye className="h-5 w-5" strokeWidth={1.5} />}
            </button>
          </div>

          {/* Remember / Forgot */}
          <div className="flex items-center justify-between px-1 py-2">
            <label className="flex items-center space-x-3 cursor-pointer group">
              <div className={`w-4 h-4 rounded-[4px] border flex items-center justify-center transition-colors ${rememberMe ? 'bg-blue-600 border-blue-600' : 'border-slate-600 bg-transparent group-hover:border-blue-400'}`}>
                 {rememberMe && <div className="w-2 h-2 bg-white rounded-[2px]" />}
              </div>
              <input type="checkbox" className="hidden" checked={rememberMe} onChange={() => setRememberMe(!rememberMe)} />
              <span className="text-[12px] font-medium text-slate-300">Remember me</span>
            </label>
            <button type="button" onClick={onForgotPassword} className="text-[12px] font-medium text-[#3B82F6] hover:text-blue-400 transition-colors">
              Forgot Password?
            </button>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full h-[60px] rounded-xl mt-2 relative group overflow-hidden disabled:opacity-70 disabled:hover:scale-100"
          >
            <div className="absolute inset-0 bg-gradient-to-b from-[#3B82F6] to-[#1D4ED8] transition-all group-hover:scale-[1.02]" />
            {/* Inner top highlight for 3D effect */}
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-white/30" />
            <div className="absolute inset-0 flex items-center justify-center space-x-2 text-white font-bold text-[14px] tracking-[0.1em]">
              <span>{loading ? 'AUTHENTICATING...' : 'SIGN IN'}</span>
              {!loading && <LuArrowRight className="w-5 h-5" strokeWidth={2} />}
            </div>
          </button>
        </form>

        {/* Security Section */}
        <div className="mt-8 pt-5 border-t border-slate-700/50 relative z-10">
          <div className="flex items-center justify-center mb-6 opacity-80">
            <div className="h-[1px] bg-slate-700/50 flex-1" />
            <span className="px-4 text-[9px] font-bold text-slate-400 tracking-[0.2em] whitespace-nowrap">SECURE ACCESS PROTOCOL</span>
            <div className="h-[1px] bg-slate-700/50 flex-1" />
          </div>
          
          <div className="flex justify-between px-2 mb-6">
            <SecurityBadge icon={LuLock} title="End-to-End Encryption" />
            <SecurityBadge icon={LuShield} title="Multi-Layer Security" />
            <SecurityBadge icon={LuFileCheck} title="Audit Logged" />
          </div>

          {/* Bottom Message */}
          <div className="flex items-center bg-gradient-to-r from-[#0B1220]/80 to-[#0A101C]/80 rounded-xl p-4 border border-white/5 group shadow-inner">
            <div className="w-10 h-10 rounded-full flex items-center justify-center mr-4 shrink-0 border border-blue-500/20 bg-blue-500/5 relative overflow-hidden">
              <div className="absolute inset-0 bg-blue-500/10 opacity-0 group-hover:opacity-100 transition-opacity" />
              <LuFingerprint className="w-5 h-5 text-blue-400 group-hover:text-blue-300 transition-colors" strokeWidth={1.5} />
            </div>
            <div className="text-[11px] text-slate-400 leading-[1.6]">
              Every action is monitored.<br />
              Every login is logged.<br />
              Every investigation <span className="text-blue-400 font-semibold">matters</span>.
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
