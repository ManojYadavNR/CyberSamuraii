import { useEffect, useMemo, useState } from 'react';
import { fetchApifyInstagramComments, fetchIgPostMedia, fetchInstagramTopCommenters, type TopCommenter } from '../api/samurai';
import { InstagramTimelinePanel } from './InstagramTimelinePanel';
import { useInvestigationStore } from '../store/investigationStore';
import { friendlyLinkLabel, resolveMediaUrl, resolveVideoUrl } from '../lib/mediaUrl';
import {
  externalVisitUrl,
  facebookProfileUrl,
  instagramProfileUrl,
  instagramPublicPostUrl,
  instagramPublicProfileUrl,
} from '../lib/socialUrls';
import {
  dedupeSamuraiMedia,
  facebookItemVisitUrl,
  formatCount,
  cleanFbDisplayName,
  isCleanFbDisplayName,
  isDisplayableSamuraiMedia,
  buildIgPostUrl,
  collectIgPostUrls,
  mapApifyComments,
  mediaEngagement,
  normalizeComments,
  pickMediaUrl,
  postEngagement,
  postPreviewUrl,
  resolveFbBiography,
  resolveIgBiography,
  samuraiIntelFromResult,
  samuraiMediaKey,
  type SamuraiComment,
} from '../lib/samuraiIntelView';
import {
  isRecordVideo,
  mediaPreviewFromRecord,
  mediaPreviewUrlCandidates,
  posterFromPost,
  posterFromRecord,
  SamuraiLinksRow,
  videoSourceFromPost,
  videoSourceFromRecord,
} from '../lib/samuraiDataRender';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

const IG_MAX_POSTS = 10;
const IG_INITIAL_VISIBLE = 6;

function SamuraiSectionHeader({
  title,
  subtitle,
  accent = 'blue',
}: {
  title: string;
  subtitle?: string;
  accent?: 'blue' | 'pink' | 'amber';
}) {
  const titleColor = accent === 'pink'
    ? 'text-pink-400'
    : accent === 'amber'
      ? 'text-amber-300'
      : 'text-blue-400';
  const borderColor = accent === 'pink'
    ? 'border-pink-500/30'
    : accent === 'amber'
      ? 'border-amber-500/30'
      : 'border-blue-500/30';
  return (
    <div className={`border-b pb-2 ${borderColor}`}>
      <h4 className={`text-xs font-bold uppercase tracking-wider ${titleColor}`}>{title}</h4>
      {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
    </div>
  );
}

function FbPhotoGrid({
  items,
  sectionKey,
}: {
  items: Record<string, unknown>[];
  sectionKey: string;
}) {
  if (!items.length) return null;
  const hasEmbeds = items.some((item) => item.render_as === 'facebook_embed');
  return (
    <div
      className={
        hasEmbeds
          ? 'grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
          : 'grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5'
      }
    >
      {items.map((item, idx) => (
        <FbMediaCard key={`${sectionKey}_${samuraiMediaKey(item)}_${item.fbid || idx}`} item={item} index={idx} />
      ))}
    </div>
  );
}

function MediaPreview({
  url,
  alt,
  isVideo,
  posterUrl,
  openHref,
  imageCandidates,
  showExternalLink = true,
  compact = false,
  clickToPlay = false,
}: {
  url?: string;
  alt: string;
  isVideo?: boolean;
  posterUrl?: string;
  openHref?: string;
  imageCandidates?: string[];
  showExternalLink?: boolean;
  compact?: boolean;
  clickToPlay?: boolean;
}) {
  const [failIdx, setFailIdx] = useState(0);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);

  const imageSources = useMemo(() => {
    if (isVideo) return [];
    const raw = imageCandidates?.length
      ? imageCandidates
      : [posterUrl, url].filter(Boolean) as string[];
    const resolved = raw
      .map((candidate) => resolveMediaUrl(candidate))
      .filter(Boolean) as string[];
    return [...new Set(resolved)];
  }, [imageCandidates, isVideo, posterUrl, url]);

  const imageSrc = imageSources[failIdx];
  const videoSrc = resolveVideoUrl(isVideo ? url : undefined);
  const video = isVideo && Boolean(videoSrc);
  const visitHref = openHref ? (externalVisitUrl(openHref) || openHref) : undefined;
  const poster = imageSrc || resolveMediaUrl(posterUrl);

  if (video && videoSrc && !failed) {
    if (clickToPlay && !playing) {
      return (
        <button
          type="button"
          onClick={() => setPlaying(true)}
          className={`group relative w-full overflow-hidden rounded-lg border border-slate-700 bg-black text-left ${
            compact ? 'aspect-square' : 'aspect-[9/16] max-h-[28rem]'
          }`}
        >
          {poster ? (
            <img
              src={poster}
              alt={alt}
              className="h-full w-full object-contain"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="flex h-full min-h-[12rem] items-center justify-center bg-slate-950 text-slate-500">
              Video preview
            </div>
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-black/35 transition group-hover:bg-black/45">
            <span className="flex h-14 w-14 items-center justify-center rounded-full border border-white/30 bg-black/50 text-2xl text-white shadow-lg">
              ▶
            </span>
          </div>
        </button>
      );
    }
    return (
      <video
        src={videoSrc}
        controls
        playsInline
        autoPlay={playing}
        preload="metadata"
        poster={poster}
        className="aspect-[9/16] max-h-[28rem] w-full rounded-lg border border-slate-700 bg-black object-contain"
        onError={() => setFailed(true)}
      />
    );
  }

  if (imageSrc && !failed) {
    return (
      <img
        src={imageSrc}
        alt={alt}
        className={compact
          ? 'aspect-square h-full w-full object-cover'
          : 'max-h-96 w-full rounded-lg border border-slate-700 bg-slate-950 object-contain'}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => {
          if (failIdx + 1 < imageSources.length) {
            setFailIdx((idx) => idx + 1);
            return;
          }
          setFailed(true);
        }}
      />
    );
  }

  return (
    <div className={`flex flex-col items-center justify-center gap-2 bg-slate-950/60 px-4 text-center text-xs text-slate-500 ${compact ? 'aspect-square' : 'aspect-video max-h-48 rounded-lg border border-dashed border-slate-700'}`}>
      <span>{compact ? 'Loading failed' : 'Preview unavailable in-app'}</span>
      {showExternalLink && visitHref && (
        <a href={visitHref} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">
          {friendlyLinkLabel(visitHref)} ↗
        </a>
      )}
    </div>
  );
}

function EngagementBar({
  likes,
  views,
  comments,
  duration,
}: {
  likes?: number;
  views?: number;
  comments?: number;
  duration?: number;
}) {
  const hasAny = likes != null || views != null || comments != null || duration != null;
  if (!hasAny) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 pt-2 text-xs text-slate-300">
      {likes != null && <span><span className="text-pink-400">♥</span> {formatCount(likes)} likes</span>}
      {views != null && <span><span className="text-cyan-400">▶</span> {formatCount(views)} views</span>}
      {comments != null && <span><span className="text-slate-400">💬</span> {formatCount(comments)} comments</span>}
      {duration != null && <span><span className="text-slate-500">⏱</span> {duration}s</span>}
    </div>
  );
}

function formatCommentTime(value?: string): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function CommentRow({ comment, depth = 0 }: { comment: SamuraiComment; depth?: number }) {
  const replies = comment.replies ?? [];
  const username = comment.username?.replace(/^@+/, '');
  const profileHref = username ? instagramPublicProfileUrl(username) : undefined;
  return (
    <div className={depth > 0 ? 'ml-4 border-l-2 border-pink-500/20 pl-3' : ''}>
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/50 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          {username && profileHref && (
            <a
              href={profileHref}
              target="_blank"
              rel="noreferrer noopener"
              className="font-semibold text-pink-300 hover:underline"
            >
              @{username}
            </a>
          )}
          {username && !profileHref && (
            <span className="font-semibold text-pink-300">@{username}</span>
          )}
          {comment.timestamp && <span>{formatCommentTime(comment.timestamp)}</span>}
          {comment.like_count != null && <span>♥ {formatCount(comment.like_count)}</span>}
          {comment.replies_count != null && comment.replies_count > 0 && (
            <span className="text-slate-600">{formatCount(comment.replies_count)} replies</span>
          )}
          {comment.comment_url && (
            <a href={comment.comment_url} target="_blank" rel="noreferrer noopener" className="text-cyan-500/80 hover:underline">
              link ↗
            </a>
          )}
        </div>
        {comment.text && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{comment.text}</p>}
      </div>
      {replies.length > 0 && (
        <div className="mt-2 space-y-2">
          {replies.map((reply, idx) => (
            <CommentRow key={`${reply.username}_${idx}_${depth}`} comment={reply} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function CommentsPanel({
  comments: initialComments,
  commentCount,
  sessionHint,
  postUrl,
}: {
  comments: SamuraiComment[];
  commentCount?: number;
  sessionHint?: string;
  postUrl?: string;
}) {
  const [open, setOpen] = useState(false);
  const [comments, setComments] = useState(initialComments);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchedViaApify, setFetchedViaApify] = useState(false);

  useEffect(() => {
    setComments(initialComments);
    setFetchedViaApify(false);
    setFetchError(null);
    setOpen(false);
  }, [initialComments, postUrl]);

  const total = commentCount ?? comments.length;
  const displayCount = fetchedViaApify ? comments.length : total;
  const canFetchApify = Boolean(postUrl);
  if (!total && comments.length === 0 && !canFetchApify) return null;

  const loadApifyComments = async () => {
    if (!postUrl || loading) return;
    setOpen(true);
    setLoading(true);
    setFetchError(null);
    try {
      const res = await fetchApifyInstagramComments(postUrl, { resultsLimit: 15, includeReplies: true });
      const mapped = mapApifyComments(res.comments);
      setComments(mapped);
      setFetchedViaApify(true);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : 'Failed to load comments');
    } finally {
      setLoading(false);
    }
  };

  const subtitle = fetchedViaApify
    ? `${formatCount(comments.length)} loaded from post`
    : comments.length > 0
      ? `${formatCount(comments.length)} from scrape`
      : canFetchApify
        ? 'Load full comments to fetch text and replies'
        : undefined;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-800/80 bg-slate-950/40">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800/60 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          aria-expanded={open}
        >
          <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-[10px] ${
            open ? 'border-pink-500/40 bg-pink-500/10 text-pink-300' : 'border-slate-700 bg-slate-900 text-slate-500'
          }`}
          >
            {open ? '▾' : '▸'}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200">
              Comments
              <span className="ml-1.5 font-normal text-slate-500">({formatCount(displayCount)})</span>
            </p>
            {subtitle && (
              <p className="mt-0.5 truncate text-[11px] text-slate-500">{subtitle}</p>
            )}
          </div>
        </button>
        {canFetchApify && (
          <button
            type="button"
            onClick={loadApifyComments}
            disabled={loading}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
          >
            {loading ? 'Loading…' : fetchedViaApify ? 'Refresh' : 'Load full comments'}
          </button>
        )}
      </div>

      {fetchError && (
        <p className="mx-3 mt-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {fetchError}
        </p>
      )}

      {open && (
        <div className="space-y-2 px-3 py-3">
          {loading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-slate-800/60 bg-slate-950/50 px-3 py-6 text-sm text-slate-400">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
              Loading comments…
            </div>
          )}
          {!loading && comments.length > 0 && (
            <>
              {fetchedViaApify && (
                <p className="text-[11px] text-cyan-400/80">
                  Loaded {comments.length} comment{comments.length === 1 ? '' : 's'}
                  {postUrl ? ` · ${postUrl.replace(/^https?:\/\//, '')}` : ''}
                </p>
              )}
              {comments.map((c, idx) => (
                <CommentRow key={`${c.username}_${idx}_${c.timestamp || ''}`} comment={c} />
              ))}
            </>
          )}
          {!loading && comments.length === 0 && (
            <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/90">
              {sessionHint || 'No comment text from Samurai scrape. Click "Load full comments" to fetch them.'}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ProfileBio({
  bio,
  externalUrl,
  hint,
}: {
  bio: string;
  externalUrl?: string;
  hint?: string;
}) {
  return (
    <div className="mt-2">
      {bio ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{bio}</p>
      ) : (
        <p className="text-sm italic text-slate-500">
          {hint || 'Bio not available from public scrape.'}
        </p>
      )}
      {externalUrl && (
        <a href={externalUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-xs text-cyan-400 hover:underline">
          {externalUrl.replace(/^https?:\/\//, '')} ↗
        </a>
      )}
    </div>
  );
}

function extractIgShortcode(url?: string, shortcode?: string): string | undefined {
  if (shortcode) return shortcode;
  if (!url) return undefined;
  const match = url.match(/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]+)/i);
  return match?.[1];
}

function FacebookEmbedFrame({
  slug,
  height = 520,
  tabs = 'timeline',
}: {
  slug: string;
  height?: number;
  tabs?: 'timeline' | 'photos' | 'timeline,photos';
}) {
  const profileUrl = facebookProfileUrl(slug);
  const src = `https://www.facebook.com/plugins/page.php?href=${encodeURIComponent(profileUrl)}&tabs=${encodeURIComponent(tabs)}&width=540&height=${height}&small_header=false&adapt_container_width=true&hide_cover=false&show_facepile=false`;
  return (
    <iframe
      title={`Facebook ${slug} ${tabs}`}
      src={src}
      className="w-full rounded-xl border border-blue-500/25 bg-slate-950"
      style={{ minHeight: height }}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
    />
  );
}

function InstagramEmbedFrame({ username, height = 480 }: { username: string; height?: number }) {
  const clean = username.trim().replace(/^@+/, '').split(/[/?#]/)[0];
  const src = `https://www.instagram.com/${encodeURIComponent(clean)}/embed/`;
  return (
    <iframe
      title={`Instagram @${clean}`}
      src={src}
      className="w-full rounded-xl border border-pink-500/25 bg-black"
      style={{ minHeight: height }}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
    />
  );
}

function InstagramProfileEmbedPanel({
  username,
  height = 420,
  compact = false,
}: {
  username: string;
  height?: number;
  compact?: boolean;
}) {
  const clean = username.trim().replace(/^@+/, '').split(/[/?#]/)[0];
  if (!clean) return null;
  const profileVisit = instagramPublicProfileUrl(clean);
  return (
    <div className="space-y-2">
      {!compact && (
        <p className="text-[11px] text-slate-500">
          In-app preview below. Use the button to open the full profile on Instagram.
        </p>
      )}
      <InstagramEmbedFrame username={clean} height={height} />
      <a
        href={profileVisit}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-[11px] font-semibold text-pink-200 hover:bg-pink-500/20"
      >
        View profile on Instagram ↗
      </a>
    </div>
  );
}

function InstagramPostEmbed({ shortcode, url }: { shortcode?: string; url?: string }) {
  const code = extractIgShortcode(url, shortcode);
  if (!code) return null;
  return (
    <iframe
      title={`Instagram post ${code}`}
      src={`https://www.instagram.com/p/${encodeURIComponent(code)}/embed`}
      className="w-full rounded-lg border border-pink-500/20 bg-black"
      style={{ minHeight: 420 }}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
    />
  );
}

function isFacebookLoginWallText(text: string): boolean {
  const low = text.toLowerCase();
  return (
    low.includes('log in to facebook')
    || low.includes('email address or mobile')
    || low.includes('email or phone')
    || low.includes('forgotten password')
    || low.includes('create new account')
    || low.includes('explore the things you love')
  );
}

function SimilarProfileCard({ entry }: { entry: Record<string, unknown> }) {
  const username = String(entry.username || '').replace(/^@/, '');
  const profileUrlRaw = String(entry.profile_url || '');
  const isInstagram = profileUrlRaw.includes('instagram.com');
  const profileUrl = externalVisitUrl(
    pickMediaUrl(entry.profile_url as string)
    || (isInstagram ? instagramProfileUrl(username) : facebookProfileUrl(username)),
  );
  const avatar = resolveMediaUrl(entry.profile_pic_url as string);
  const photos = (entry.photos as Record<string, unknown>[] | undefined) ?? [];
  const posts = (entry.posts as Record<string, unknown>[] | undefined) ?? photos;
  const previewItems = posts
    .filter((item) => {
      const text = String(item.text || item.caption || '').trim();
      return !isFacebookLoginWallText(text);
    })
    .slice(0, 2);
  const isPrivate = entry.is_private === true;
  const displayName = cleanFbDisplayName(String(entry.full_name || ''), username);

  return (
    <article className="overflow-hidden rounded-xl border border-amber-500/25 bg-amber-500/5">
      <div className="flex items-start gap-3 p-3">
        {avatar ? (
          <img src={avatar} alt="" className="h-14 w-14 shrink-0 rounded-full border border-amber-400/30 object-cover" loading="lazy" referrerPolicy="no-referrer" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
        ) : isInstagram && username ? (
          <div className="h-14 w-14 shrink-0 overflow-hidden rounded-full border border-amber-400/30">
            <InstagramEmbedFrame username={username} height={56} />
          </div>
        ) : (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-dashed border-amber-500/30 bg-slate-950 text-lg text-amber-400/60">
            {isInstagram ? '📸' : '📘'}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-white">{displayName}</p>
          {username && <p className="font-mono text-xs text-amber-200/80">@{username}</p>}
          {isPrivate && <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">Private account</p>}
          {entry.photo_count != null && Number(entry.photo_count) > 0 && (
            <p className="mt-1 text-[11px] text-slate-500">{Number(entry.photo_count)} preview item(s)</p>
          )}
          {profileUrl && (
            <a href={profileUrl} target="_blank" rel="noreferrer noopener" className="mt-2 inline-flex rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/20">
              {isInstagram ? 'Open on Instagram ↗' : 'Open on Facebook ↗'}
            </a>
          )}
        </div>
      </div>
      {previewItems.length > 0 && (
        <div className="grid grid-cols-2 gap-1 border-t border-amber-500/15 p-2">
          {previewItems.map((item, idx) => {
            const src = resolveMediaUrl(
              mediaPreviewFromRecord(item)
              || pickMediaUrl(item.thumbnail as string, item.display_url as string, item.url as string),
            );
            const text = String(item.text || item.caption || '').trim();
            const postUrl = externalVisitUrl(pickMediaUrl(item.live_url as string, item.url as string));
            if (src) {
              return (
                <a key={idx} href={postUrl || profileUrl} target="_blank" rel="noreferrer noopener" className="block overflow-hidden rounded">
                  <img src={src} alt="" className="aspect-square w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
                </a>
              );
            }
            if (text && !isFacebookLoginWallText(text)) {
              return (
                <div key={idx} className="flex aspect-square items-center justify-center rounded border border-amber-500/15 bg-slate-950/70 p-2 text-center text-[10px] leading-snug text-slate-300">
                  {text.slice(0, 120)}
                </div>
              );
            }
            return null;
          })}
        </div>
      )}
    </article>
  );
}

function CarouselMediaGrid({
  media,
  openHref,
}: {
  media: Record<string, unknown>[];
  openHref?: string;
}) {
  const slides = media
    .map((item) => mediaPreviewFromRecord(item) || pickMediaUrl(item.display_url as string, item.url as string, item.thumbnail as string))
    .filter(Boolean) as string[];
  if (!slides.length) return null;
  return (
    <div className="overflow-hidden rounded-lg border border-pink-500/20 bg-slate-950/40">
      <div className="flex snap-x snap-mandatory gap-2 overflow-x-auto p-2">
        {slides.map((src, idx) => (
          <div key={idx} className="w-full min-w-[85%] shrink-0 snap-center sm:min-w-[calc(50%-4px)]">
            <MediaPreview url={src} alt={`Photo ${idx + 1} of ${slides.length}`} showExternalLink={false} />
          </div>
        ))}
      </div>
      <p className="border-t border-pink-500/10 px-2 py-1.5 text-center text-[11px] text-slate-500">
        {slides.length} photos in this post — swipe to view all
      </p>
      {openHref && (
        <div className="border-t border-pink-500/10 px-2 py-2 text-center">
          <a
            href={externalVisitUrl(openHref) || openHref}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[11px] font-semibold text-pink-300 hover:underline"
          >
            Open on Instagram ↗
          </a>
        </div>
      )}
    </div>
  );
}

function FbTimelineCard({ post, index }: { post: Record<string, unknown>; index: number }) {
  const image = resolveMediaUrl(pickMediaUrl(post.image_url as string, post.thumbnail as string));
  const visit = pickMediaUrl(post.url as string, post.live_url as string);
  const text = String(post.text || post.caption || '').trim();

  return (
    <article className="overflow-hidden rounded-xl border border-blue-500/20 bg-blue-500/5 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="muted">#{index + 1}</Badge>
        <Badge variant="info">Timeline</Badge>
      </div>
      {image && (
        <img src={image} alt="" className="mb-3 max-h-64 w-full rounded-lg border border-slate-700 object-contain" loading="lazy" referrerPolicy="no-referrer" />
      )}
      {text && <p className="whitespace-pre-wrap text-sm text-slate-300">{text}</p>}
      {visit && (
        <a href={visit} target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-500/20">
          Open on Facebook ↗
        </a>
      )}
    </article>
  );
}

function IgPostCard({
  post,
  index,
  sessionHint,
}: {
  post: Record<string, unknown>;
  index: number;
  sessionHint?: string;
}) {
  const isReel = Boolean(post.is_video) || post.type === 'Reel' || post.type === 'Video';
  const videoSrc = videoSourceFromPost(post);
  const poster = posterFromPost(post);
  const visit = externalVisitUrl(pickMediaUrl(post.live_url as string, post.url as string));
  const shortcode = extractIgShortcode(visit, post.shortcode as string | undefined);
  const postUrl = buildIgPostUrl({ url: visit, shortcode, isReel });
  const media = (post.media as Record<string, unknown>[] | undefined) ?? [];
  const isCarousel = !isReel && (media.length > 1 || post.type === 'Carousel');
  const comments = normalizeComments(post.comments);
  const engagement = postEngagement(post);
  const hashtags = (post.hashtags as string[] | undefined) ?? [];
  const mentions = (post.mentions as string[] | undefined) ?? [];

  const [resolvedVideo, setResolvedVideo] = useState<string | undefined>(videoSrc);
  const [resolvedPoster, setResolvedPoster] = useState<string | undefined>(poster);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [mediaError, setMediaError] = useState(false);

  useEffect(() => {
    setResolvedVideo(videoSrc);
    setResolvedPoster(poster);
    setMediaError(false);
  }, [videoSrc, poster, shortcode]);

  useEffect(() => {
    if (!isReel || videoSrc || !shortcode) return;
    let cancelled = false;
    setMediaLoading(true);
    fetchIgPostMedia(shortcode)
      .then((data) => {
        if (cancelled) return;
        if (data.video_url) setResolvedVideo(data.video_url);
        if (data.display_url) setResolvedPoster(data.display_url);
        if (!data.video_url && !data.display_url) setMediaError(true);
      })
      .catch(() => {
        if (!cancelled) setMediaError(true);
      })
      .finally(() => {
        if (!cancelled) setMediaLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isReel, videoSrc, shortcode]);

  const preview = isReel ? resolvedVideo : postPreviewUrl(post as never);
  const showEmbed = !isReel && !preview && !isCarousel && Boolean(shortcode);

  return (
    <article className="overflow-hidden rounded-xl border border-pink-500/20 bg-pink-500/5">
      <div className="p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="muted">#{index + 1}</Badge>
          <Badge variant={isReel ? 'info' : 'muted'}>{isReel ? 'Reel / Video' : String(post.type || 'Post')}</Badge>
          {isCarousel && <Badge variant="info">{media.length || 'Multi'}-photo carousel</Badge>}
          {post.shortcode != null && <Badge variant="muted">{String(post.shortcode)}</Badge>}
        </div>
        {showEmbed && shortcode ? (
          <InstagramPostEmbed shortcode={shortcode} url={visit} />
        ) : isCarousel ? (
          <CarouselMediaGrid media={media} openHref={visit} />
        ) : mediaLoading && isReel && !preview ? (
          <div className="flex aspect-[9/16] max-h-[28rem] items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-sm text-slate-400">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-pink-400/30 border-t-pink-400" />
            <span className="ml-2">Loading reel…</span>
          </div>
        ) : (
          <MediaPreview
            url={preview}
            alt={String(post.caption || 'Instagram post')}
            isVideo={isReel}
            posterUrl={resolvedPoster || poster}
            clickToPlay={isReel}
            showExternalLink={false}
          />
        )}
        {isReel && mediaError && !preview && !mediaLoading && (
          <p className="mt-2 text-xs text-amber-300/90">
            Could not load reel video in-app. Use Open on Instagram below.
          </p>
        )}
        <EngagementBar likes={engagement.likes} views={engagement.views} comments={engagement.comments} duration={engagement.duration} />
        {post.caption != null && String(post.caption) && (
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{String(post.caption)}</p>
        )}
        {hashtags.length > 0 && <p className="mt-2 text-xs text-pink-300/80">{hashtags.map((h) => `#${h}`).join(' ')}</p>}
        {mentions.length > 0 && <p className="mt-1 text-xs text-slate-400">Mentions: {mentions.map((m) => `@${m}`).join(', ')}</p>}
        <CommentsPanel comments={comments} commentCount={engagement.comments} sessionHint={sessionHint} postUrl={postUrl} />
        {visit && (
          <div className="mt-3 flex flex-wrap gap-2">
            <a
              href={externalVisitUrl(visit) || visit}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-xs font-semibold text-pink-200 hover:bg-pink-500/20"
            >
              Open on Instagram ↗
            </a>
          </div>
        )}
      </div>
    </article>
  );
}

function FbMediaCard({
  item,
  index,
}: {
  item: Record<string, unknown>;
  index: number;
}) {
  const isVideo = isRecordVideo(item);
  const videoSrc = videoSourceFromRecord(item);
  const poster = posterFromRecord(item);
  const preview = isVideo ? videoSrc : mediaPreviewFromRecord(item);
  const visit = facebookItemVisitUrl(item);
  const engagement = mediaEngagement(item);
  const caption = String(item.title || item.caption || item.text || '').trim();
  const imageCandidates = mediaPreviewUrlCandidates(item, { isVideo });
  const embedUrl = String(item.embed_url || '');
  const useEmbed = item.render_as === 'facebook_embed' && Boolean(embedUrl);

  return (
    <article className="group overflow-hidden rounded-lg border border-blue-500/20 bg-slate-950/50 transition hover:border-blue-400/40">
      <div className={`relative bg-slate-950 ${useEmbed ? 'min-h-[280px]' : 'aspect-square'}`}>
        {useEmbed ? (
          <iframe
            title={caption || `Facebook photo ${index + 1}`}
            src={embedUrl}
            className="h-[280px] w-full border-0 bg-slate-950"
            loading="lazy"
            sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
            referrerPolicy="no-referrer"
          />
        ) : (
          <MediaPreview
            url={preview}
            alt={caption || `Facebook photo ${index + 1}`}
            isVideo={isVideo}
            posterUrl={poster}
            openHref={visit}
            imageCandidates={imageCandidates}
            showExternalLink
            compact
          />
        )}
      </div>
      <div className="p-2">
        <EngagementBar likes={engagement.likes} views={engagement.views} comments={engagement.comments} />
        {caption && <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{caption}</p>}
        {visit && (
          <a
            href={visit}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-1 inline-flex text-[11px] font-semibold text-blue-300 hover:underline"
          >
            Open on Facebook ↗
          </a>
        )}
      </div>
    </article>
  );
}

function postTypeLabel(type?: string): string {
  if (type === 'reel') return 'Reel';
  if (type === 'tv') return 'IGTV';
  if (type === 'post') return 'Post';
  return 'Media';
}

function CollapsibleBlock({
  title,
  subtitle,
  open,
  onToggle,
  children,
  accent = 'slate',
}: {
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  accent?: 'cyan' | 'pink' | 'slate';
}) {
  const accentBorder = accent === 'cyan'
    ? 'border-cyan-500/20'
    : accent === 'pink'
      ? 'border-pink-500/20'
      : 'border-slate-800/80';
  return (
    <div className={`overflow-hidden rounded-xl border bg-slate-950/40 ${accentBorder}`}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-slate-900/50"
      >
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-[10px] ${
          open ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300' : 'border-slate-700 bg-slate-900 text-slate-500'
        }`}
        >
          {open ? '−' : '+'}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold tracking-wide text-slate-200">{title}</p>
          {subtitle && <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p>}
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-800/60 px-4 pb-4 pt-3">
          {children}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'default' | 'cyan' | 'pink';
}) {
  const toneClass = tone === 'cyan'
    ? 'border-cyan-500/25 bg-gradient-to-br from-cyan-950/40 to-slate-950/60'
    : tone === 'pink'
      ? 'border-pink-500/25 bg-gradient-to-br from-pink-950/30 to-slate-950/60'
      : 'border-slate-800/80 bg-slate-950/50';
  return (
    <div className={`rounded-xl border px-4 py-3 ${toneClass}`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{value}</p>
      {hint && <p className="mt-1 text-[10px] text-slate-500">{hint}</p>}
    </div>
  );
}

function TopCommentersPanel({
  postUrls,
  profileUsername,
}: {
  postUrls: string[];
  profileUsername: string;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [overviewOpen, setOverviewOpen] = useState(true);
  const [commentersOpen, setCommentersOpen] = useState(true);
  const [stats, setStats] = useState<{
    posts_analyzed: number;
    total_comments: number;
    unique_commenters: number;
    top_commenters: TopCommenter[];
  } | null>(null);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);

  if (postUrls.length === 0) return null;

  const loadStats = async () => {
    if (loading) return;
    setLoading(true);
    setError(null);
    setPanelOpen(true);
    try {
      const res = await fetchInstagramTopCommenters(postUrls, {
        profileUsername,
        resultsLimit: 15,
        topN: 10,
      });
      setStats({
        posts_analyzed: res.posts_analyzed,
        total_comments: res.total_comments,
        unique_commenters: res.unique_commenters,
        top_commenters: res.top_commenters,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load comment statistics');
    } finally {
      setLoading(false);
    }
  };

  const summaryLine = stats
    ? `${formatCount(stats.posts_analyzed)} posts · ${formatCount(stats.total_comments)} comments · ${formatCount(stats.top_commenters.length)} top users`
    : `${postUrls.length} posts ready to analyze`;

  return (
    <div className="overflow-hidden rounded-2xl border border-cyan-500/20 bg-gradient-to-b from-cyan-950/25 via-slate-950/40 to-slate-950/20 shadow-lg shadow-cyan-950/20">
      <div className="flex flex-wrap items-center gap-3 border-b border-cyan-500/15 bg-cyan-950/20 px-4 py-3">
        <button
          type="button"
          onClick={() => setPanelOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-expanded={panelOpen}
        >
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-sm transition ${
            panelOpen
              ? 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200'
              : 'border-slate-700 bg-slate-900/80 text-slate-400'
          }`}
          >
            {panelOpen ? '▾' : '▸'}
          </span>
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-white">Comment statistics</h4>
            <p className="mt-0.5 truncate text-[11px] text-slate-400">
              {summaryLine}
              {profileUsername ? ` · excl. @${profileUsername}` : ''}
            </p>
          </div>
        </button>
        <button
          type="button"
          onClick={loadStats}
          disabled={loading}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-100 transition hover:border-cyan-400/50 hover:bg-cyan-500/25 disabled:opacity-50"
        >
          {loading ? 'Loading…' : stats ? 'Refresh' : 'Analyze'}
        </button>
      </div>

      {panelOpen && (
        <div className="space-y-4 p-4">
          {error && (
            <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </p>
          )}

          {!stats && !loading && !error && (
            <p className="rounded-xl border border-dashed border-slate-700/80 bg-slate-950/30 px-4 py-6 text-center text-sm text-slate-400">
              Click <span className="font-semibold text-cyan-300">Analyze</span> to load comment stats for {postUrls.length} posts.
            </p>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-800/60 bg-slate-950/40 px-4 py-8 text-sm text-slate-400">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
              Loading statistics…
            </div>
          )}

          {stats && !loading && (
            <div className="space-y-3">
              <CollapsibleBlock
                title="Overview"
                subtitle="Summary across all analyzed posts"
                open={overviewOpen}
                onToggle={() => setOverviewOpen((v) => !v)}
                accent="cyan"
              >
                <div className="grid gap-3 sm:grid-cols-3">
                  <StatCard label="Posts analyzed" value={formatCount(stats.posts_analyzed)} tone="cyan" />
                  <StatCard label="Comments scraped" value={formatCount(stats.total_comments)} />
                  <StatCard
                    label="Unique commenters"
                    value={formatCount(stats.unique_commenters)}
                    tone="pink"
                    hint={`Top ${stats.top_commenters.length} shown below`}
                  />
                </div>
              </CollapsibleBlock>

              <CollapsibleBlock
                title="Top commenters"
                subtitle={stats.top_commenters.length === 0 ? 'No comments found' : 'Ranked by total comments · click username to open profile on Instagram'}
                open={commentersOpen}
                onToggle={() => setCommentersOpen((v) => !v)}
                accent="pink"
              >
                {stats.top_commenters.length === 0 ? (
                  <p className="text-xs text-slate-400">No comments returned for these posts.</p>
                ) : (
                  <ol className="space-y-2">
                    {stats.top_commenters.map((user, idx) => {
                      const open = expandedUser === user.username;
                      const postsPct = stats.posts_analyzed > 0
                        ? Math.round((user.posts_count / stats.posts_analyzed) * 100)
                        : 0;
                      const maxComments = stats.top_commenters[0]?.comment_count || 1;
                      const barPct = Math.round((user.comment_count / maxComments) * 100);
                      return (
                        <li
                          key={user.username}
                          className="overflow-hidden rounded-xl border border-slate-800/70 bg-slate-950/50 transition hover:border-pink-500/20"
                        >
                          <button
                            type="button"
                            onClick={() => setExpandedUser(open ? null : user.username)}
                            className="flex w-full items-start gap-3 px-3 py-3 text-left hover:bg-slate-900/40"
                          >
                            <span className="mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500/20 to-pink-500/20 text-[11px] font-bold text-cyan-200">
                              {idx + 1}
                            </span>
                            {user.profile_pic_url ? (
                              <img
                                src={user.profile_pic_url}
                                alt=""
                                className="h-11 w-11 shrink-0 rounded-full border-2 border-pink-500/25 object-cover ring-2 ring-slate-900"
                                loading="lazy"
                                referrerPolicy="no-referrer"
                              />
                            ) : (
                              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 border-slate-700 bg-slate-900 text-sm font-semibold text-pink-300">
                                {(user.username[0] || '?').toUpperCase()}
                              </div>
                            )}
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <a
                                  href={instagramPublicProfileUrl(user.username)}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  onClick={(e) => e.stopPropagation()}
                                  className="font-semibold text-pink-200 hover:underline"
                                >
                                  @{user.username}
                                </a>
                                {user.is_verified && <Badge variant="success">Verified</Badge>}
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2 py-0.5 text-[10px] text-slate-300">
                                  {formatCount(user.comment_count)} comments
                                </span>
                                <span className="rounded-full border border-pink-500/20 bg-pink-500/10 px-2 py-0.5 text-[10px] text-pink-200">
                                  {formatCount(user.posts_count)} posts
                                </span>
                                {(user.reply_count ?? 0) > 0 && (
                                  <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2 py-0.5 text-[10px] text-slate-300">
                                    {formatCount(user.reply_count)} replies
                                  </span>
                                )}
                              </div>
                              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-cyan-500/70 to-pink-500/70"
                                  style={{ width: `${barPct}%` }}
                                />
                              </div>
                              {stats.posts_analyzed > 1 && (
                                <p className="mt-1.5 text-[10px] text-slate-500">
                                  Active on {postsPct}% of posts ({user.posts_count}/{stats.posts_analyzed})
                                </p>
                              )}
                            </div>
                            <span className="mt-2 shrink-0 text-xs text-slate-500">{open ? '▾' : '▸'}</span>
                          </button>
                          {open && (
                            <div className="space-y-3 border-t border-slate-800/70 bg-slate-950/30 px-3 py-3">
                              <a
                                href={instagramPublicProfileUrl(user.username)}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-xs font-semibold text-pink-200 hover:bg-pink-500/20"
                              >
                                View @{user.username} on Instagram ↗
                              </a>
                              <p className="text-[11px] text-slate-500">
                                {formatCount(user.posts_count)} posts ·
                                {' '}{formatCount(user.top_level_count ?? user.comment_count)} top-level ·
                                {' '}{formatCount(user.reply_count ?? 0)} replies
                                {(user.total_likes ?? 0) > 0 && ` · ♥ ${formatCount(user.total_likes)}`}
                              </p>
                              {user.by_post.map((group) => (
                                <div key={group.post_url} className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3">
                                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                    <Badge variant="muted">{postTypeLabel(group.post_type)}</Badge>
                                    <span className="font-mono font-semibold text-slate-200">{group.shortcode || 'post'}</span>
                                    <span className="text-pink-300/90">
                                      {formatCount(group.comment_count ?? group.comments.length)} from this user
                                    </span>
                                    <a
                                      href={instagramPublicPostUrl(group.post_url) || group.post_url}
                                      target="_blank"
                                      rel="noreferrer noopener"
                                      className="ml-auto text-cyan-400 hover:underline"
                                    >
                                      Open ↗
                                    </a>
                                  </div>
                                  <ul className="mt-2 space-y-2">
                                    {group.comments.map((c, cIdx) => (
                                      <li
                                        key={`${group.post_url}_${cIdx}`}
                                        className="rounded-lg border border-slate-800/50 bg-slate-900/40 px-3 py-2"
                                      >
                                        {c.is_reply && (
                                          <span className="mb-1 inline-block rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                            Reply
                                          </span>
                                        )}
                                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">{c.text || '—'}</p>
                                        <div className="mt-1.5 flex flex-wrap gap-2 text-[11px] text-slate-500">
                                          {c.timestamp && <span>{formatCommentTime(c.timestamp)}</span>}
                                          {c.like_count != null && <span>♥ {formatCount(c.like_count)}</span>}
                                        </div>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ol>
                )}
              </CollapsibleBlock>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function InstagramSection({ data }: { data: Record<string, unknown> }) {
  const profile = (data.profile as Record<string, unknown> | undefined) ?? {};
  const links = (data.links as Record<string, unknown> | undefined) ?? {};
  const notes = (data.notes as Record<string, unknown> | undefined) ?? {};
  const allPosts = (data.recent_posts as Record<string, unknown>[] | undefined) ?? [];
  const reels = (data.reels as Record<string, unknown>[] | undefined) ?? [];
  const similar = (data.similar_profiles as Record<string, unknown>[] | undefined) ?? [];
  const posts = allPosts.filter(
    (post) => !post.is_video && post.type !== 'Reel' && post.type !== 'Video',
  );
  const cappedPosts = useMemo(() => posts.slice(0, IG_MAX_POSTS), [posts]);
  const cappedReels = useMemo(() => reels.slice(0, IG_MAX_POSTS), [reels]);
  const totalMedia = cappedPosts.length + cappedReels.length;
  const [mediaExpanded, setMediaExpanded] = useState(false);
  const initialPhotoBatch = useMemo(
    () => cappedPosts.slice(0, Math.min(IG_INITIAL_VISIBLE, cappedPosts.length)),
    [cappedPosts],
  );
  const photosRemaining = Math.max(0, cappedPosts.length - initialPhotoBatch.length);
  const visiblePhotos = mediaExpanded ? cappedPosts : initialPhotoBatch;
  const visibleReels = mediaExpanded
    ? cappedReels
    : (cappedPosts.length === 0 ? cappedReels.slice(0, IG_INITIAL_VISIBLE) : []);
  const hiddenReelCount = mediaExpanded
    ? 0
    : (cappedPosts.length === 0
      ? Math.max(0, cappedReels.length - IG_INITIAL_VISIBLE)
      : cappedReels.length);
  const hasMoreMedia = photosRemaining > 0 || hiddenReelCount > 0;
  const apiResponse = data.api_response as Record<string, unknown> | undefined;
  const bio = resolveIgBiography(profile, apiResponse);
  const authenticated = data.authenticated === true;
  const scrapeLimited = data.scrape_limited === true;
  const username = String(profile.username || '');
  const hasServerMedia = posts.length > 0 || reels.length > 0;
  const usePublicEmbed = !authenticated;
  const sessionHint = String(
    notes.comment_text
    || notes.session_help
    || '',
  );
  const avatar = resolveMediaUrl(profile.profile_pic_url as string);
  const externalUrl = String(profile.external_url || '').trim();
  const profileVisit = externalVisitUrl(instagramProfileUrl(username));
  const postUrls = useMemo(
    () => collectIgPostUrls(cappedPosts, cappedReels, IG_MAX_POSTS),
    [cappedPosts, cappedReels],
  );

  return (
    <div className="space-y-4">
      {usePublicEmbed && !hasServerMedia && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
          <p className="font-semibold text-slate-200">Public Instagram view</p>
          <p className="mt-1 text-xs text-slate-400">
            Profile, posts, and reels load via Instagram embed (same as instagram.com). Close any login popup to browse.
          </p>
        </div>
      )}

      {scrapeLimited && !hasServerMedia && username && (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-xs text-amber-100/90">
          Server could not pull CDN images for this account. Showing live Instagram embed below.
        </div>
      )}

      <div className="flex flex-wrap items-start gap-4 rounded-xl border border-pink-500/25 bg-gradient-to-r from-pink-950/30 to-slate-900/40 p-4">
        {avatar ? (
          <img src={avatar} alt="" className="h-20 w-20 shrink-0 rounded-full border-2 border-pink-400/40 object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : username ? (
          <div className="h-28 w-28 shrink-0 overflow-hidden rounded-full border-2 border-pink-400/30">
            <InstagramEmbedFrame username={username} height={112} />
          </div>
        ) : (
          <div className="flex h-20 w-20 items-center justify-center rounded-full border border-dashed border-pink-400/30 bg-slate-950 text-2xl text-pink-400/50">📸</div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-white">{String(profile.full_name || profile.username || 'Instagram')}</h3>
            {profile.is_verified === true && <Badge variant="success">Verified</Badge>}
            {profile.is_private === true && <Badge variant="warn">Private</Badge>}
            {profile.is_business === true && <Badge variant="info">Business</Badge>}
          </div>
          {profile.username != null && <p className="font-mono text-sm text-pink-300">@{String(profile.username)}</p>}
          <ProfileBio
            bio={bio}
            externalUrl={externalUrl.startsWith('http') ? externalUrl : undefined}
            hint={String(notes.biography || 'Bio may require IG_SESSIONID for some accounts.')}
          />
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
            {profile.follower_count != null && <span>{Number(profile.follower_count).toLocaleString()} followers</span>}
            {profile.following_count != null && <span>{Number(profile.following_count).toLocaleString()} following</span>}
            {profile.media_count != null && <span>{Number(profile.media_count).toLocaleString()} posts</span>}
            {profile.id != null && <span>ID: {String(profile.id)}</span>}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <SamuraiLinksRow links={links} />
            {profileVisit && (
              <a href={profileVisit} target="_blank" rel="noreferrer noopener" className="inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-xs font-semibold text-pink-200 hover:bg-pink-500/20">
                Open profile on Instagram ↗
              </a>
            )}
          </div>
        </div>
      </div>

      {username && (
        <InstagramTimelinePanel profileUsername={username} />
      )}

      {postUrls.length > 0 && (
        <TopCommentersPanel postUrls={postUrls} profileUsername={username} />
      )}

      {username && usePublicEmbed && !hasServerMedia && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-pink-400">Profile & recent posts</h4>
          <InstagramEmbedFrame username={username} height={520} />
        </div>
      )}

      {(cappedPosts.length > 0 || cappedReels.length > 0) && (
        <div className="space-y-6 rounded-xl border border-pink-500/25 bg-pink-950/10 p-4">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-pink-500/20 pb-3">
            <div>
              <SamuraiSectionHeader
                title={`@${username || 'target'} — profile posts`}
                subtitle={
                  totalMedia < IG_MAX_POSTS
                    ? `Showing all ${totalMedia} available post${totalMedia === 1 ? '' : 's'}`
                    : `Up to ${IG_MAX_POSTS} recent posts from this account`
                }
                accent="pink"
              />
            </div>
            <p className="text-[11px] text-slate-500">
              {mediaExpanded
                ? `Showing ${visiblePhotos.length + visibleReels.length} of ${totalMedia}`
                : `Showing ${visiblePhotos.length} of ${totalMedia} — photos first`}
            </p>
          </div>

          {visiblePhotos.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Photos & carousels ({visiblePhotos.length}{!mediaExpanded && cappedPosts.length > visiblePhotos.length ? ` / ${cappedPosts.length}` : ''})
              </h5>
              <div className="grid gap-4 md:grid-cols-2">
                {visiblePhotos.map((post, idx) => (
                  <IgPostCard key={String(post.shortcode || post.url || idx)} post={post} index={idx} sessionHint={sessionHint} />
                ))}
              </div>
            </div>
          )}

          {visibleReels.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Reels & videos ({visibleReels.length})
              </h5>
              <div className="grid gap-4 md:grid-cols-2">
                {visibleReels.map((post, idx) => (
                  <IgPostCard
                    key={String(post.shortcode || post.url || idx)}
                    post={post}
                    index={visiblePhotos.length + idx}
                    sessionHint={sessionHint}
                  />
                ))}
              </div>
            </div>
          )}

          {hasMoreMedia && !mediaExpanded && (
            <button
              type="button"
              onClick={() => setMediaExpanded(true)}
              className="w-full rounded-xl border border-dashed border-pink-500/30 bg-pink-500/5 px-4 py-3 text-sm font-semibold text-pink-200 transition hover:border-pink-400/40 hover:bg-pink-500/10"
            >
              Load reels & more posts
              {' '}
              ({photosRemaining + hiddenReelCount} more)
            </button>
          )}

          {mediaExpanded && hasMoreMedia && (
            <button
              type="button"
              onClick={() => setMediaExpanded(false)}
              className="text-xs font-semibold text-slate-500 hover:text-slate-300"
            >
              Show fewer posts
            </button>
          )}
        </div>
      )}

      {similar.length > 0 && (
        <div className="space-y-3 rounded-xl border border-amber-500/20 bg-amber-950/10 p-4">
          <SamuraiSectionHeader
            title={`Similar accounts (${similar.length})`}
            subtitle="Other Instagram profiles with a similar username pattern"
            accent="amber"
          />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {similar.slice(0, 8).map((entry, idx) => (
              <SimilarProfileCard key={String(entry.username || idx)} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FacebookSection({
  data,
  facebookSlug,
}: {
  data: Record<string, unknown>;
  facebookSlug?: string;
}) {
  const profile = (data.profile as Record<string, unknown> | undefined) ?? {};
  const personal = {
    ...((profile.personal_details as Record<string, unknown> | undefined) ?? {}),
    ...((data.personal_details as Record<string, unknown> | undefined) ?? {}),
  };
  const links = (data.links as Record<string, unknown> | undefined) ?? {};
  const photos = (data.photos as Record<string, unknown>[] | undefined) ?? [];
  const videos = (data.videos as Record<string, unknown>[] | undefined) ?? [];
  const reels = (data.reels as Record<string, unknown>[] | undefined) ?? [];
  const timeline = (data.timeline_posts as Record<string, unknown>[] | undefined) ?? [];
  const friends = (data.friends as Record<string, unknown>[] | undefined) ?? [];
  const similar = (data.similar_profiles as Record<string, unknown>[] | undefined) ?? [];
  const bio = resolveFbBiography(profile, personal);
  // Only the Facebook profile username — never the Instagram seed handle.
  const targetSlug = String(facebookSlug || profile.username || data.username || '').replace(/^@/, '');
  const showName = cleanFbDisplayName(String(profile.full_name || ''), targetSlug);
  const profilePhotos = (profile.photos as Record<string, unknown>[] | undefined) ?? [];
  const allPhotos = dedupeSamuraiMedia([...photos, ...profilePhotos]).filter(isDisplayableSamuraiMedia);
  const slugLow = targetSlug.toLowerCase();

  // Strict: profile picture + this profile's album only (never "Others named …").
  const isOwnMedia = (item: Record<string, unknown>) => {
    if (item.is_target_profile === false) return false;
    const source = String(item.source || '');
    const owner = String(item.owner_username || '').toLowerCase().replace(/^@/, '');
    if (owner && owner !== slugLow) return false;
    if (item.type === 'profile_picture') return true;
    if (
      (source === 'photos_page' || source === 'photos_box' || source === 'photos_by')
      && item.is_target_profile === true
    ) return true;
    if (source === 'facebook_graph_picture' || source === 'profile_picture') return true;
    return false;
  };

  const ownPhotos = allPhotos.filter(isOwnMedia);
  const profilePicRaw = pickMediaUrl(
    profile.profile_pic_url as string,
    profile.profile_pic as string,
    links.profile_picture as string,
  );
  const profilePicKey = profilePicRaw ? samuraiMediaKey({ url: profilePicRaw }) : null;

  // Gallery = this user's posts (exclude avatar duplicate when other posts exist).
  const postPhotos = ownPhotos.filter((p) => {
    if (p.type === 'profile_picture') return false;
    if (profilePicKey && samuraiMediaKey(p) === profilePicKey) return false;
    return true;
  });
  const galleryPhotos = postPhotos.length > 0 ? postPhotos : ownPhotos;
  const dedupedVideos = dedupeSamuraiMedia(videos.filter((v) => isOwnMedia(v) && isDisplayableSamuraiMedia(v)));
  const dedupedReels = dedupeSamuraiMedia(reels.filter((r) => isOwnMedia(r) && isDisplayableSamuraiMedia(r)));
  const targetTimeline = timeline.filter((p) => isOwnMedia(p));
  const hasServerMedia = galleryPhotos.length > 0
    || dedupedVideos.length > 0
    || dedupedReels.length > 0
    || targetTimeline.length > 0;
  const personalEntries = Object.entries(personal).filter(
    ([key, v]) => key !== 'Similar Profiles' && v != null && String(v).trim(),
  );
  const othersNamedLabel = String(personal['Similar Profiles'] || '').trim();
  const hasIntel = hasServerMedia || personalEntries.length > 0 || similar.length > 0;
  // Only show the empty-embed banner when we truly have no Facebook intel.
  const embedOnly = data.embed_only === true && !hasIntel;
  const profileVisit = facebookProfileUrl(targetSlug);
  const avatar = resolveMediaUrl(
    pickMediaUrl(
      profile.profile_pic_url as string,
      profile.profile_pic as string,
      links.profile_picture as string,
      ownPhotos.find((p) => p.type === 'profile_picture')?.url as string,
      ownPhotos.find((p) => p.type === 'profile_picture')?.live_url as string,
      galleryPhotos[0]?.thumbnail as string,
      galleryPhotos[0]?.url as string,
      galleryPhotos[0]?.live_url as string,
    ),
  );

  const hasTargetMedia = galleryPhotos.length > 0
    || dedupedReels.length > 0
    || dedupedVideos.length > 0
    || targetTimeline.length > 0;

  return (
    <div className="space-y-4">
      {embedOnly && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
          <p className="font-semibold text-slate-200">Public Facebook view</p>
          <p className="mt-1 text-xs text-slate-400">
            Server could not pull Facebook media right now. Profile loads below via Facebook embed in your browser.
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-start gap-4 rounded-xl border border-blue-500/25 bg-gradient-to-r from-blue-950/30 to-slate-900/40 p-4">
        {avatar ? (
          <img src={avatar} alt="" className="h-20 w-20 rounded-full border-2 border-blue-400/40 object-cover" loading="lazy" referrerPolicy="no-referrer" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
        ) : (
          <div className="flex h-20 w-20 items-center justify-center rounded-full border border-dashed border-blue-400/30 bg-slate-950 text-2xl text-blue-400/50">📘</div>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-white">{showName}</h3>
          {targetSlug && (
            <p className="font-mono text-sm text-blue-300">@{targetSlug}</p>
          )}
          <ProfileBio
            bio={bio && isCleanFbDisplayName(bio) ? bio : ''}
            hint={personalEntries.length ? undefined : 'Bio may be hidden for locked profiles without Facebook session.'}
          />
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
            {profile.like_count != null && <span>{Number(profile.like_count).toLocaleString()} likes</span>}
            {profile.friend_count != null && <span>{Number(profile.friend_count).toLocaleString()} friends</span>}
            {profile.talking_about_count != null && <span>{Number(profile.talking_about_count).toLocaleString()} talking about</span>}
          </div>
          <div className="mt-3">
            <SamuraiLinksRow links={links} />
            {profileVisit && (
              <a href={profileVisit} target="_blank" rel="noreferrer noopener" className="mt-2 inline-flex rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-500/20">
                Open profile on Facebook ↗
              </a>
            )}
          </div>
        </div>
      </div>

      {targetSlug && embedOnly && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-400">Profile & timeline</h4>
          <FacebookEmbedFrame slug={targetSlug} height={560} />
        </div>
      )}

      {personalEntries.length > 0 && (
        <div className="rounded-xl border border-emerald-500/25 bg-emerald-950/10 p-4">
          <SamuraiSectionHeader
            title="Personal information"
            subtitle={`About @${targetSlug}`}
            accent="blue"
          />
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            {personalEntries.map(([key, value]) => (
              <div key={key} className="rounded-lg border border-slate-800/60 bg-slate-950/40 px-3 py-2">
                <dt className="text-[10px] font-bold uppercase tracking-wider text-emerald-400/80">{key}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-slate-100">{String(value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {targetSlug && (
        <div className="space-y-6 rounded-xl border border-blue-500/25 bg-blue-950/10 p-4">
          <SamuraiSectionHeader
            title={`${showName} — photos, reels & albums`}
            subtitle={`Only @${targetSlug} — this profile only (not similar accounts)`}
            accent="blue"
          />

          {/* Verified scrapable media for this profile only (profile picture / public album bytes). */}
          {galleryPhotos.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Collected photos of @{targetSlug} ({galleryPhotos.length})
              </h5>
              <FbPhotoGrid items={galleryPhotos} sectionKey="target_photos" />
            </div>
          )}

          {dedupedReels.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Reels ({dedupedReels.length})
              </h5>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {dedupedReels.map((item, idx) => (
                  <FbMediaCard key={`reel_${samuraiMediaKey(item)}`} item={item} index={idx} />
                ))}
              </div>
            </div>
          )}

          {dedupedVideos.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Videos ({dedupedVideos.length})
              </h5>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {dedupedVideos.map((item, idx) => (
                  <FbMediaCard key={`video_${samuraiMediaKey(item)}`} item={item} index={idx} />
                ))}
              </div>
            </div>
          )}

          {targetTimeline.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Posts & albums ({targetTimeline.length})
              </h5>
              <div className="grid gap-4 sm:grid-cols-2">
                {targetTimeline.map((post, idx) => (
                  <FbTimelineCard key={idx} post={post} index={idx} />
                ))}
              </div>
            </div>
          )}

          {galleryPhotos.length === 0 && (
            <p className="text-xs text-slate-500">
              No public album photos could be collected for @{targetSlug} yet. Profile picture is shown above when available.
            </p>
          )}

          {profileVisit && (
            <a
              href={`${profileVisit.replace(/\/?$/, '')}/photos`}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex text-xs font-semibold text-blue-300 hover:underline"
            >
              Open @{targetSlug} photos on Facebook ↗
            </a>
          )}
        </div>
      )}

      {similar.length > 0 && (
        <div className="space-y-3 rounded-xl border border-amber-500/20 bg-amber-950/10 p-4">
          <SamuraiSectionHeader
            title={othersNamedLabel || `Similar accounts (${similar.length})`}
            subtitle={othersNamedLabel
              ? `Profiles Facebook lists under "${othersNamedLabel}"`
              : `Other profiles matching ${showName}`}
            accent="amber"
          />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {similar.slice(0, 8).map((entry, idx) => (
              <SimilarProfileCard key={String(entry.username || idx)} entry={entry} />
            ))}
          </div>
        </div>
      )}

      {/* Non-target / "Others named …" media is intentionally not shown in Photos —
          only @targetSlug media appears above. Similar accounts are listed separately. */}

      {friends.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-400">Friends ({friends.length})</h4>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {friends.map((friend, idx) => {
              const pic = resolveMediaUrl(pickMediaUrl(friend.profile_pic_url as string, friend.photo as string));
              const name = String(friend.name || friend.full_name || friend.username || `Friend ${idx + 1}`);
              const href = pickMediaUrl(friend.profile_url as string, friend.url as string);
              return (
                <div key={idx} className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                  {pic ? <img src={pic} alt="" className="h-10 w-10 rounded-full object-cover" loading="lazy" referrerPolicy="no-referrer" /> : <span className="text-lg">👤</span>}
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200">{name}</p>
                    {href && (
                      <a href={href} target="_blank" rel="noreferrer" className="text-[11px] text-blue-400 hover:underline">Open profile ↗</a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function facebookDisplayPayload(
  fb: Record<string, unknown> | null | undefined,
  slug?: string | null,
): Record<string, unknown> | null {
  if (fb && typeof fb === 'object') {
    // Normalize profile username/name so the UI never shows the Instagram seed handle.
    const profile = { ...((fb.profile as Record<string, unknown> | undefined) ?? {}) };
    const target = String(slug || profile.username || '').replace(/^@/, '');
    if (target) profile.username = target;
    if (!isCleanFbDisplayName(String(profile.full_name || ''))) {
      profile.full_name = cleanFbDisplayName(String(profile.full_name || ''), target);
    }
    return { ...fb, profile };
  }
  const target = (slug || '').trim().replace(/^@/, '');
  if (!target) return null;
  const profileUrl = `https://www.facebook.com/${encodeURIComponent(target)}`;
  return {
    embed_only: true,
    profile: {
      username: target,
      full_name: cleanFbDisplayName(null, target),
      profile_url: profileUrl,
    },
    links: { profile: profileUrl },
    photos: [],
    videos: [],
    reels: [],
    timeline_posts: [],
    friends: [],
    similar_profiles: [],
    personal_details: {},
  };
}

export function SamuraiSocialPanel() {
  const result = useInvestigationStore((s) => s.result);
  const intel = useMemo(() => samuraiIntelFromResult(result), [result]);

  if (!result || !intel) return null;

  const ig = intel.instagram as Record<string, unknown> | null | undefined;
  const fbRaw = intel.facebook as Record<string, unknown> | null | undefined;
  const fbSlug = String(
    intel.facebook_slug
    || (fbRaw?.profile as Record<string, unknown> | undefined)?.username
    || '',
  ).replace(/^@/, '');
  const fb = facebookDisplayPayload(fbRaw, fbSlug);
  const hasIg = Boolean(ig);
  const hasFb = Boolean(fb);

  if (!hasIg && !hasFb) {
    return (
      <EmptyState
        icon="🥷"
        title="Samurai — no social data"
        description={
          [intel.instagram_error, intel.facebook_error].filter(Boolean).join(' · ')
          || 'Samurai ran but returned no Instagram or Facebook profile data.'
        }
      />
    );
  }

  const fbUsername = String(
    (fb?.profile as Record<string, unknown> | undefined)?.username
    || fbSlug
    || '',
  );
  const fbDisplayName = cleanFbDisplayName(
    String((fb?.profile as Record<string, unknown> | undefined)?.full_name || ''),
    fbUsername,
  );
  const igUsername = String(
    (ig?.profile as Record<string, unknown> | undefined)?.username
    || intel.username
    || '',
  ).replace(/^@/, '');

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-pink-950/40 via-slate-900 to-blue-950/40 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-fuchsia-400/90">Samurai deep social intel</p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          {hasIg && hasFb
            ? `Instagram @${igUsername} · Facebook @${fbUsername}`
            : hasFb
              ? `Facebook @${fbUsername}`
              : `Instagram @${igUsername}`}
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Profile, posts, photos, and reels — deduplicated gallery with in-app previews.
        </p>
        {hasFb && (
          <p className="mt-2 text-xs text-blue-400/80">
            Facebook: {fbDisplayName} · @{fbUsername}
          </p>
        )}
      </div>

      {(hasIg || hasFb) && (
        <div className="flex flex-wrap gap-2 border-b border-slate-800/80 px-5 pt-4 text-xs text-slate-500">
          {hasIg && <span className="rounded-full border border-pink-500/30 bg-pink-500/10 px-3 py-1 text-pink-200">Instagram loaded</span>}
          {hasFb && (
            <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-blue-200">
              {fbRaw ? 'Facebook loaded' : 'Facebook embed'}
            </span>
          )}
          {intel.facebook_error && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-amber-200">
              Facebook note: {intel.facebook_error}
            </span>
          )}
        </div>
      )}

      <div className="space-y-8 p-5">
        {hasIg && (
          <div id="samurai-instagram">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xl">📸</span>
              <h3 className="text-sm font-bold uppercase tracking-wider text-pink-300">Instagram intelligence</h3>
            </div>
            <InstagramSection data={ig!} />
          </div>
        )}
        {intel.instagram_error && !hasIg && (
          <p className="text-sm text-amber-400">Instagram error: {intel.instagram_error}</p>
        )}

        {hasFb && (
          <div id="samurai-facebook" className={hasIg ? 'border-t border-slate-800/80 pt-8' : ''}>
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xl">📘</span>
              <h3 className="text-sm font-bold uppercase tracking-wider text-blue-300">Facebook intelligence</h3>
              {fbUsername && (
                <span className="rounded border border-blue-500/25 bg-blue-500/10 px-2 py-0.5 font-mono text-[11px] text-blue-200">
                  @{fbUsername}
                </span>
              )}
            </div>
            <FacebookSection
              data={fb!}
              facebookSlug={fbUsername}
            />
          </div>
        )}
      </div>
    </section>
  );
}
