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

/** URL safe to open in a new tab — fixes known Facebook SERP mangling. */
export function externalVisitUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return undefined;
  return fixFacebookPostUrl(trimmed);
}
