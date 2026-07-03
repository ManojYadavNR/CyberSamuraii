import type { ReactNode } from 'react';
import { externalVisitUrl } from './socialUrls';
import { friendlyLinkLabel, isLikelyVideoUrl, resolveMediaUrl, resolveVideoUrl } from './mediaUrl';
import { isVideoUrl, pickMediaUrl } from './samuraiIntelView';

function isProbablyImageUrl(url: string): boolean {
  const low = url.toLowerCase();
  return /\.(jpg|jpeg|png|gif|webp)(\?|$)/i.test(low)
    || low.includes('cdninstagram')
    || low.includes('fbcdn')
    || low.includes('lookaside.fbsbx');
}

function formatLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ExternalLink({ url }: { url: string }) {
  const href = externalVisitUrl(url) || url;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20"
    >
      {friendlyLinkLabel(href)} ↗
    </a>
  );
}

function scalar(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span className="text-slate-500">—</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="font-mono text-slate-300">{value ? 'true' : 'false'}</span>;
  }
  if (typeof value === 'number') {
    return <span className="font-mono text-cyan-200">{value.toLocaleString()}</span>;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      const img = resolveMediaUrl(trimmed);
      const vid = resolveVideoUrl(trimmed);
      const video = isVideoUrl(trimmed) || isLikelyVideoUrl(trimmed);
      return (
        <div className="space-y-2">
          {video && vid && (
            <video
              src={vid}
              controls
              playsInline
              preload="metadata"
              className="max-h-48 w-full rounded border border-slate-700 bg-black"
              poster={!video && img ? img : undefined}
            />
          )}
          {!video && isProbablyImageUrl(trimmed) && img && (
            <img src={img} alt="" className="max-h-48 rounded border border-slate-700 object-contain" loading="lazy" referrerPolicy="no-referrer" />
          )}
          <ExternalLink url={trimmed} />
        </div>
      );
    }
    return <span className="whitespace-pre-wrap break-words text-sm text-slate-200">{trimmed}</span>;
  }
  return <span className="text-sm text-slate-200">{String(value)}</span>;
}

export function SamuraiValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500">null</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-xs text-slate-500">Empty list</span>;
    }
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={index} className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-3">
            <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-600">Item {index + 1}</p>
            <SamuraiValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) {
      return <span className="text-xs text-slate-500">Empty object</span>;
    }
    return (
      <dl className={`grid gap-2 ${depth > 0 ? '' : 'sm:grid-cols-2'}`}>
        {entries.map(([key, child]) => (
          <div key={key} className={depth === 0 && typeof child === 'object' && child !== null ? 'sm:col-span-2' : ''}>
            <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{formatLabel(key)}</dt>
            <dd className="mt-1 min-w-0">{typeof child === 'object' && child !== null ? <SamuraiValue value={child} depth={depth + 1} /> : scalar(child)}</dd>
          </div>
        ))}
      </dl>
    );
  }

  return scalar(value);
}

export function SamuraiLinksRow({ links }: { links: Record<string, unknown> }) {
  const entries = Object.entries(links).filter(([, v]) => typeof v === 'string' && v.startsWith('http'));
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, url]) => {
        const href = externalVisitUrl(String(url)) || String(url);
        return (
        <a
          key={key}
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20"
        >
          {formatLabel(key)} ↗
        </a>
        );
      })}
    </div>
  );
}

export function badgeForValue(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} items`;
  if (value && typeof value === 'object') return `${Object.keys(value).length} fields`;
  if (value === null || value === undefined || value === '') return 'empty';
  return '1 value';
}

function lookasideThumbnailUrl(url: string): string | undefined {
  const low = url.toLowerCase();
  if (!low.includes('lookaside.fbsbx.com')) return undefined;
  if (low.includes('get_thumbnail=1')) return url;
  return `${url}${url.includes('?') ? '&' : '?'}get_thumbnail=1`;
}

export function mediaPreviewFromRecord(record: Record<string, unknown>): string | undefined {
  const thumb = pickMediaUrl(
    record.preview_url as string,
    record.thumbnail_live_url as string,
    record.thumbnail as string,
    record.image_url as string,
  );
  const primary = pickMediaUrl(
    record.display_live_url as string,
    record.display_url as string,
    record.video_live_url as string,
    record.video_url as string,
    record.live_url as string,
    record.url as string,
    record.profile_pic_url as string,
  );
  const synthesizedThumb = primary ? lookasideThumbnailUrl(primary) : undefined;
  const bestThumb = thumb || synthesizedThumb;
  const primaryLow = (primary || '').toLowerCase();
  if (primaryLow.includes('lookaside.fbsbx.com') && bestThumb) {
    return bestThumb;
  }
  return primary || bestThumb;
}

export function mediaPreviewUrlCandidates(
  record: Record<string, unknown>,
  opts?: { isVideo?: boolean },
): string[] {
  if (opts?.isVideo) {
    const poster = posterFromRecord(record);
    return poster ? [poster] : [];
  }
  const primary = pickMediaUrl(
    record.preview_url as string,
    record.display_live_url as string,
    record.display_url as string,
    record.live_url as string,
    record.url as string,
    record.profile_pic_url as string,
  );
  const thumb = pickMediaUrl(
    record.thumbnail_live_url as string,
    record.thumbnail as string,
    record.image_url as string,
  );
  const synthesized = primary ? lookasideThumbnailUrl(primary) : undefined;
  const ordered = [thumb, synthesized, primary].filter(Boolean) as string[];
  return [...new Set(ordered)];
}

export function videoSourceFromPost(post: Record<string, unknown>): string | undefined {
  const video = (post.video as Record<string, unknown> | undefined) ?? {};
  return pickMediaUrl(
    video.video_live_url as string,
    video.video_url as string,
    post.video_live_url as string,
    post.video_url as string,
  );
}

export function posterFromPost(post: Record<string, unknown>): string | undefined {
  return pickMediaUrl(
    post.display_live_url as string,
    post.display_url as string,
    post.thumbnail_live_url as string,
    post.thumbnail as string,
    (post.media as Record<string, unknown>[] | undefined)?.[0]?.display_url as string,
    (post.media as Record<string, unknown>[] | undefined)?.[0]?.thumbnail as string,
  );
}

export function videoSourceFromRecord(record: Record<string, unknown>): string | undefined {
  return pickMediaUrl(
    record.video_live_url as string,
    record.video_url as string,
    record.url as string,
    record.live_url as string,
  );
}

export function posterFromRecord(record: Record<string, unknown>): string | undefined {
  return pickMediaUrl(
    record.thumbnail_live_url as string,
    record.thumbnail as string,
    record.image_url as string,
    record.display_url as string,
    record.display_live_url as string,
  );
}

export function isRecordVideo(record: Record<string, unknown>): boolean {
  return Boolean(record.is_reel) || record.type === 'video' || isVideoUrl(videoSourceFromRecord(record));
}
