/**
 * Client-side display policy — mirror backend account_confirmed / evidence gates.
 * Only data passing these checks may appear in verified account UI.
 */
import type { FieldProvenance, LinkedAccount, PlatformProfile } from '../types';

const JUNK_HANDLES = new Set([
  'user', 'users', 'profile', 'details', 'member', 'member.php', 'forum',
  'p', 'u', 'perfil', 'open', 'lover', 'accounts', 'about', 'players',
  'search', 'login', 'signup', 'register', 'index', 'home',
]);

export function normalizeAccountHandle(handle: string): string {
  return handle.replace(/^@+/, '').replace(/^~+/, '').trim().toLowerCase();
}

export function isEmailRegistrationHandle(handle: string): boolean {
  const h = normalizeAccountHandle(handle);
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(h);
}

/** Reject junk URL fragments; allow email registrations from holehe. */
export function isPlausibleAccountHandle(handle: string): boolean {
  const h = normalizeAccountHandle(handle);
  if (!h || h.length < 3) return false;
  if (isEmailRegistrationHandle(h)) return true;
  if (/^\d+$/.test(h)) return false;
  if (JUNK_HANDLES.has(h)) return false;
  if (h.length < 4 && !/\d/.test(h)) return false;
  return true;
}

/** Exclude dork-only and single platform_probe hits from verified cards. */
export function isCorroboratedSources(sources: string[]): boolean {
  if (!sources.length) return false;
  if (sources.every((s) => s === 'google_dorking')) return false;
  if (sources.length === 1 && sources[0] === 'platform_probe') return false;
  return true;
}

export function isVerifiedPlatformProfile(pp: PlatformProfile): boolean {
  if (!pp.verified) return false;
  if (!isCorroboratedSources(pp.sources ?? [])) return false;
  if (!isPlausibleAccountHandle(pp.handle || '')) return false;
  return true;
}

export function isVerifiedLinkedAccount(acct: LinkedAccount): boolean {
  if (!acct.verified) return false;
  if (!isCorroboratedSources(acct.sources ?? [])) return false;
  if (!isPlausibleAccountHandle(acct.handle || acct.url || '')) return false;
  return true;
}

/** Emails safe to show in person profile / contacts (not raw holehe noise). */
export function isDisplayableEmailField(fp: FieldProvenance): boolean {
  if (fp.source_tool === 'user_input' || fp.extraction_strategy === 'investigation_seed') return true;
  if (fp.source_tool === 'holehe') return false;
  if (
    fp.source_tool === 'google_dorking' &&
    fp.extraction_strategy !== 'username_attributed_discovery'
  ) {
    return false;
  }
  return true;
}

export function formatPlatformHandle(handle: string): string {
  const h = normalizeAccountHandle(handle);
  if (isEmailRegistrationHandle(h)) return h;
  return `@${h}`;
}
