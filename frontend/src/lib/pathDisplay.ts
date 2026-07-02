/** Hide server-local paths from investigator-facing UI. */

const LOCAL_MARKERS = ['/home/', '/tmp/', '/var/', 'data/uploads', '\\users\\', 'c:\\'];

export function isLocalPath(value: string | undefined | null): boolean {
  if (!value) return true;
  const low = value.trim().toLowerCase().replace(/\\/g, '/');
  if (low.startsWith('file:')) return true;
  if (!low.startsWith('/') && !/^[a-z]:\//.test(low)) return false;
  return LOCAL_MARKERS.some((m) => low.includes(m)) || low.includes('/uploads/') || low.includes('/tmp/');
}

export function isPublicUrl(value: string | undefined | null): boolean {
  if (!value) return false;
  const low = value.trim().toLowerCase();
  return low.startsWith('http://') || low.startsWith('https://');
}

export function formatTargetLabel(query: string, faceDetected = false): string {
  if (!isLocalPath(query)) return query;
  const base = query.replace(/\\/g, '/').split('/').pop() || 'uploaded image';
  return faceDetected ? `Person in uploaded photo (${base})` : `Uploaded image (${base})`;
}

export function publicOnly(values: string[]): string[] {
  return values.filter((v) => v && isPublicUrl(v) && !isLocalPath(v));
}

export function sanitizeProvenance(parts: (string | undefined | null)[]): string {
  return publicOnly(parts.filter(Boolean) as string[]).join(' · ');
}
