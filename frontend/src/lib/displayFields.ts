/** Shared display helpers for intelligence rows and lead cards. */

export { resolveMediaUrl, externalPageUrl } from './mediaUrl';

export function isProseField(label: string): boolean {
  const key = label.toLowerCase();
  return key === 'snippet'
    || key === 'search_snippet'
    || key.includes('bio')
    || key.includes('biograph')
    || key.includes('description')
    || key.includes('provenance');
}

export function isMediaUrl(value: string | undefined): boolean {
  if (!value) return false;
  return value.startsWith('http') || value.startsWith('/api/intel/');
}
