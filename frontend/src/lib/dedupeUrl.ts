/** Normalize URLs for cross-panel deduplication. */
export function normalizeUrlKey(url: string): string {
  try {
    const u = new URL(url);
    u.hash = '';
    u.search = '';
    return `${u.hostname}${u.pathname}`.replace(/\/$/, '').toLowerCase();
  } catch {
    return url.split('?')[0].replace(/\/$/, '').toLowerCase();
  }
}

export function dedupeByUrl<T>(items: T[], pickUrl: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const raw = pickUrl(item);
    if (!raw?.startsWith('http')) {
      out.push(item);
      continue;
    }
    const key = normalizeUrlKey(raw);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}
