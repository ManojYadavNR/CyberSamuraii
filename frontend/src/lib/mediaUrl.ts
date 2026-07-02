import { apiAssetUrl } from '../api/client';
import { useAuthStore } from '../store/authStore';
import { externalVisitUrl } from './socialUrls';

const API_MEDIA_RE = /^\/api\/intel\/(?:screenshots|image\/)/;
const PROXY_RE = /\/api\/intel\/(?:media-proxy|image-proxy)/;

function withAuthQuery(url: string): string {
  const token = useAuthStore.getState().accessToken;
  if (!token) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

function proxiedExternalUrl(url: string, kind: 'image' | 'video' | 'auto'): string {
  const base = apiAssetUrl('') ?? '';
  const isVideo = kind === 'video' || (kind === 'auto' && isLikelyVideoUrl(url));
  const proxied = isVideo
    ? `${base}/api/intel/media-proxy?url=${encodeURIComponent(url)}`
    : `${base}/api/intel/image-proxy?url=${encodeURIComponent(url)}`;
  return withAuthQuery(proxied);
}

/** Resolve investigation media for <img src> and links — proxies externals, adds auth for API assets. */
export function resolveMediaUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (!trimmed) return undefined;

  if (trimmed.startsWith('/api/')) {
    const resolved = apiAssetUrl(trimmed) ?? trimmed;
    if (API_MEDIA_RE.test(trimmed) || PROXY_RE.test(resolved)) {
      return withAuthQuery(resolved);
    }
    return resolved;
  }

  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return proxiedExternalUrl(trimmed, 'auto');
  }

  return trimmed;
}

/** Resolve video URLs for <video src> — uses media-proxy when needed. */
export function resolveVideoUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (!trimmed) return undefined;
  if (trimmed.startsWith('/api/')) {
    const resolved = apiAssetUrl(trimmed) ?? trimmed;
    return withAuthQuery(resolved);
  }
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return proxiedExternalUrl(trimmed, 'video');
  }
  return trimmed;
}

export function externalPageUrl(url: string | undefined): string | undefined {
  return externalVisitUrl(url);
}

export function isLikelyVideoUrl(url: string): boolean {
  const low = url.toLowerCase();
  if (/\.(mp4|webm|m4v)(\?|$)/i.test(low)) return true;
  if (low.includes('/video/') || low.includes('/reel/')) return true;
  if ((low.includes('fbcdn.net') || low.includes('cdninstagram.com') || low.includes('instagram.'))
    && (low.includes('/v/t') || low.includes('/o1/v/') || low.includes('efg='))) {
    return true;
  }
  return false;
}

export function friendlyLinkLabel(url: string): string {
  const low = url.toLowerCase();
  if (low.includes('instagram.com')) {
    if (low.includes('/reel/')) return 'Open reel on Instagram';
    if (low.includes('/p/') || low.includes('/tv/')) return 'Open post on Instagram';
    if (low.includes('/stories/')) return 'Open story on Instagram';
    return 'Open on Instagram';
  }
  if (low.includes('facebook.com') || low.includes('fb.com') || low.includes('fb.watch')) {
    return 'Open on Facebook';
  }
  if (isLikelyVideoUrl(url)) return 'Open video';
  if (low.includes('fbcdn.net') || low.includes('cdninstagram.com')) return 'Open media';
  return 'Open link';
}
