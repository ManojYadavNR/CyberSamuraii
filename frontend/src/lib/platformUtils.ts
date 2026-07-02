const PROFILE_PATH_SKIP = new Set([
  'p', 'reel', 'tv', 'explore', 'accounts', 'share', 'sharer', 'pages',
  'profile.php', 'www', 'posts', 'photos', 'videos', 'user', 'users',
]);

const SOCIAL_POST_RE = /\/(?:posts|photos|videos|reel|permalink)(?:\/|$)|\/(?:p|reel|tv)\/[^/?#]+/i;

export function normalizePlatformHost(urlOrHost: string): string {
  if (!urlOrHost) return '';
  const raw = urlOrHost.trim();
  let host = raw;
  if (raw.includes('://')) {
    try {
      host = new URL(raw).hostname;
    } catch {
      host = raw.split('/')[0];
    }
  } else {
    host = raw.split('/')[0];
  }
  host = host.toLowerCase();
  if (host.startsWith('www.')) host = host.slice(4);
  if (host.startsWith('m.')) host = host.slice(2);
  if (host.startsWith('in.') && host.includes('linkedin')) {
    host = host.slice(3);
  }
  return host;
}

export function platformKey(platformOrUrl: string): string {
  const host = normalizePlatformHost(platformOrUrl);
  if (!host || host === 'web') return 'web';
  const parts = host.split('.').filter(Boolean);
  if (!parts.length) return host;
  if (host.endsWith('.github.io') && parts.length >= 3) return parts[0];
  return parts.length >= 2 && parts[parts.length - 1].length <= 3 ? parts[parts.length - 2] : parts[0];
}

export function platformLabel(platformOrUrl: string): string {
  const host = normalizePlatformHost(platformOrUrl);
  if (!host || host === 'web') return 'Web';
  if (host === 'youtu.be') return 'YouTube';
  if (host === 't.me' || host === 'telegram.me') return 'Telegram';
  if (host === 'x.com' || host === 'twitter.com') return 'X';
  if (host.endsWith('.github.io')) {
    const sub = host.split('.')[0];
    return sub.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
  const parts = host.split('.').filter(Boolean);
  if (!parts.length) return host;
  const label = parts.length >= 2 && parts[parts.length - 1].length <= 3 ? parts[parts.length - 2] : parts[0];
  return label.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function platformFromUrl(url: string): string {
  return platformKey(url);
}

export function isSocialPostUrl(url: string): boolean {
  return Boolean(url && SOCIAL_POST_RE.test(url));
}

export function profileSlugFromUrl(url: string): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url.includes('://') ? url : `https://${url}`);
    let path = parsed.pathname.replace(/^\/+/, '').replace(/\/+$/, '');
    if (!path) return null;
    if (path.startsWith('in/')) {
      const parts = path.split('/');
      return parts[1]?.toLowerCase() || null;
    }
    if (path.includes('@')) {
      return path.split('@', 2)[1]?.split('/')[0]?.toLowerCase() || null;
    }
    const host = normalizePlatformHost(parsed.hostname);
    if (host.endsWith('tumblr.com') && parsed.hostname && !parsed.hostname.startsWith('www.')) {
      return parsed.hostname.split('.')[0].toLowerCase();
    }
    const segment = path.split('/')[0].toLowerCase();
    if (PROFILE_PATH_SKIP.has(segment)) return null;
    return segment;
  } catch {
    return null;
  }
}

export function openLinkLabel(url: string): string {
  const label = platformLabel(url);
  if (label === 'Web') return 'Open original page →';
  return `View on ${label} →`;
}

export function groupByPlatform<T>(
  items: T[],
  resolve: (item: T) => string = (item) => platformKey(String((item as { platform?: string; url?: string }).platform || (item as { url?: string }).url || 'web')),
): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = resolve(item) || 'web';
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }
  return new Map([...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0])));
}
