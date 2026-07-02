import type { IconType } from 'react-icons';
import {
  LuBriefcase,
  LuClipboardCheck,
  LuCompass,
  LuFileOutput,
  LuFolderOpen,
  LuFolderPlus,
  LuFolders,
  LuGlobe,
  LuKeyRound,
  LuLayoutDashboard,
  LuLogOut,
  LuNetwork,
  LuPaperclip,
  LuRadar,
  LuScrollText,
  LuSearch,
  LuSettings,
  LuShieldCheck,
  LuTriangleAlert,
  LuUsers,
  LuWrench,
  LuZap,
} from 'react-icons/lu';
import type { AppPage } from '../../store/uiStore';

export const NAV_ICONS: Record<AppPage, IconType> = {
  dashboard: LuLayoutDashboard,
  'investigator-dashboard': LuCompass,
  cases: LuFolderOpen,
  'case-workspace': LuBriefcase,
  investigations: LuSearch,
  graph: LuNetwork,
  evidence: LuPaperclip,
  reports: LuFileOutput,
  'osint-framework': LuGlobe,
  tools: LuWrench,
  'intel-api': LuZap,
  'pending-approvals': LuShieldCheck,
  audit: LuScrollText,
  admin: LuSettings,
  'password-reset': LuKeyRound,
  'change-password': LuKeyRound,
};

export function NavIcon({ page, className = '' }: { page: AppPage; className?: string }) {
  const Icon = NAV_ICONS[page];
  return <Icon className={className} aria-hidden />;
}

export {
  LuClipboardCheck,
  LuFolderPlus,
  LuFolders,
  LuLogOut,
  LuRadar,
  LuTriangleAlert,
  LuUsers,
};
