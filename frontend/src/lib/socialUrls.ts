/** Repair malformed Facebook photo paths from SERP (photos/a.slug → photos/slug). */
export function fixFacebookPostUrl(url: string): string {
  if (!url || !url.toLowerCase().includes('facebook.com')) return url;
  let raw = url.trim();
  if (!raw.startsWith('http://') && !raw.startsWith('https://')) {
    raw = `https://${raw}`;
  }
  try {
    const parsed = new URL(raw);
    parsed.pathname = parsed.pathname.replace(/\/photos\/a\.([a-zA-Z][\w-]+)/gi, '/photos/$1');
    if (!parsed.hostname.startsWith('www.') && parsed.hostname.endsWith('facebook.com')) {
      parsed.hostname = `www.${parsed.hostname}`;
    }
    return parsed.toString();
  } catch {
    return raw.replace(/\/photos\/a\.([a-zA-Z][\w-]+)/gi, '/photos/$1');
  }
}

/** Canonical public Instagram profile URL. */
export function instagramProfileUrl(username: string): string {
  const clean = username.trim().replace(/^@+/, '').split(/[/?#]/)[0];
  if (!clean) return 'https://www.instagram.com/';
  return `https://www.instagram.com/${encodeURIComponent(clean)}/`;
}

/** Canonical public Facebook profile URL. */
export function facebookProfileUrl(slug: string): string {
  const clean = slug.trim().replace(/^@+/, '').split(/[/?#]/)[0];
  if (!clean) return 'https://www.facebook.com/';
  if (clean.startsWith('profile.php')) {
    return `https://www.facebook.com/${clean}`;
  }
  return `https://www.facebook.com/${encodeURIComponent(clean)}/`;
}

function normalizeInstagramUrl(url: string): string {
  try {
    const parsed = new URL(url.startsWith('http') ? url : `https://${url}`);
    if (parsed.pathname.includes('/accounts/login')) {
      const next = parsed.searchParams.get('next');
      if (next?.includes('instagram.com')) {
        return normalizeInstagramUrl(next);
      }
    }
    if (!parsed.hostname.startsWith('www.') && parsed.hostname.endsWith('instagram.com')) {
      parsed.hostname = `www.${parsed.hostname}`;
    }
    return parsed.toString();
  } catch {
    return url;
  }
}

function normalizeFacebookUrl(url: string): string {
  return fixFacebookPostUrl(url.startsWith('http') ? url : `https://${url}`);
}

/** URL safe to open in a new tab — fixes known Facebook SERP mangling. */
export function externalVisitUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return undefined;
  const low = trimmed.toLowerCase();
  if (low.includes('instagram.com')) {
    return normalizeInstagramUrl(trimmed);
  }
  if (low.includes('facebook.com') || low.includes('fb.com')) {
    return normalizeFacebookUrl(trimmed);
  }
  return trimmed;
}
