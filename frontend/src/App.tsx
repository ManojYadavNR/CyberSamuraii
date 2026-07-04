import { useEffect, useState } from 'react';
import { fetchMe } from './api/auth';
import { ForgotPasswordPage } from './components/ForgotPasswordPage';
import { LoginPage } from './components/LoginPage';
import { AppShell } from './layout/AppShell';
import { useAuthStore } from './store/authStore';
import { useStartup } from './hooks/useStartup';
import { StartupIntro } from './components/startup/StartupIntro';

export default function App() {
  const enterpriseAuth = useAuthStore((s) => s.enterpriseAuth);
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const authenticated = !enterpriseAuth || Boolean(accessToken && user);
  const setEnterpriseAuth = useAuthStore((s) => s.setEnterpriseAuth);
  const setSession = useAuthStore((s) => s.setSession);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const [authView, setAuthView] = useState<'login' | 'forgot-password'>('login');
  
  const { isFinished, finishStartup } = useStartup();

  useEffect(() => {
    const base = import.meta.env.VITE_API_URL || '';
    fetch(`${base}/api/auth/status`)
      .then(async (r) => {
        if (!r.ok) {
          setEnterpriseAuth(true);
          return;
        }
        const d = await r.json();
        setEnterpriseAuth(d.enterprise_auth !== false);
      })
      .catch(() => setEnterpriseAuth(true));
  }, [setEnterpriseAuth]);

  useEffect(() => {
    if (!enterpriseAuth || !accessToken) return;
    fetchMe()
      .then((user) => {
        if (refreshToken) setSession(accessToken, refreshToken, user);
        else useAuthStore.setState({ user });
      })
      .catch(() => { /* session refresh handler will clear on 401 */ });
    import('./lib/permissions').then(({ loadRbacConfig }) => loadRbacConfig().catch(() => undefined));
  }, [enterpriseAuth, accessToken, refreshToken, setSession]);

  return (
    <>
      {!isFinished && <StartupIntro onComplete={finishStartup} />}
      
      {enterpriseAuth && !authenticated ? (
        authView === 'forgot-password' ? (
          <ForgotPasswordPage onBack={() => setAuthView('login')} />
        ) : (
          <LoginPage onForgotPassword={() => setAuthView('forgot-password')} />
        )
      ) : (
        <AppShell />
      )}
    </>
  );
}
