import React, { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { Background } from './auth/Background';
import { BrandSection } from './auth/BrandSection';
import { LoginCard } from './auth/LoginCard';
import { StatusBar } from './auth/StatusBar';

const API_BASE = import.meta.env.VITE_API_URL || '';

interface LoginPageProps {
  onForgotPassword: () => void;
}

export function LoginPage({ onForgotPassword }: LoginPageProps) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);

  const handleSubmit = async (e: React.FormEvent, username: string, pass: string) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password: pass }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || 'Invalid credentials');
      }
      const data = await res.json();
      setSession(data.access_token, data.refresh_token, data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050814] text-white font-sans selection:bg-blue-500/30 flex flex-col relative overflow-hidden">
      <Background />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col lg:flex-row pb-16 lg:pb-16 h-full items-center">
        
        {/* Left Panel - Branding (58% width on desktop) */}
        <div className="w-full lg:w-[58%] flex flex-col justify-center px-6 py-12 lg:px-12 relative z-10 lg:h-full">
          <BrandSection />
        </div>
        
        {/* Right Panel - Login Card (42% width on desktop) */}
        <div className="w-full lg:w-[42%] flex items-center justify-center px-6 py-8 lg:pr-24 relative z-10 lg:h-full">
          <LoginCard 
            onSubmit={handleSubmit}
            onForgotPassword={onForgotPassword}
            loading={loading}
            error={error}
          />
        </div>

      </div>

      <StatusBar />
    </div>
  );
}
