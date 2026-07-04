import { useMemo, useState } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { friendlyLinkLabel, resolveMediaUrl, resolveVideoUrl } from '../lib/mediaUrl';
import { externalVisitUrl, facebookProfileUrl, instagramProfileUrl } from '../lib/socialUrls';
import {
  dedupeSamuraiMedia,
  facebookItemVisitUrl,
  formatCount,
  cleanFbDisplayName,
  isCleanFbDisplayName,
  isDisplayableSamuraiMedia,
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
}: {
  url?: string;
  alt: string;
  isVideo?: boolean;
  posterUrl?: string;
  openHref?: string;
  imageCandidates?: string[];
  showExternalLink?: boolean;
  compact?: boolean;
}) {
  const [failIdx, setFailIdx] = useState(0);
  const [failed, setFailed] = useState(false);

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

  if (video && videoSrc && !failed) {
    return (
      <video
        src={videoSrc}
        controls
        playsInline
        preload="metadata"
        poster={imageSrc}
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

function CommentRow({ comment }: { comment: SamuraiComment }) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-950/50 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        {comment.username && <span className="font-semibold text-pink-300">@{comment.username}</span>}
        {comment.timestamp && <span>{comment.timestamp}</span>}
        {comment.like_count != null && <span>♥ {formatCount(comment.like_count)}</span>}
      </div>
      {comment.text && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{comment.text}</p>}
    </div>
  );
}

function CommentsPanel({
  comments,
  commentCount,
  sessionHint,
}: {
  comments: SamuraiComment[];
  commentCount?: number;
  sessionHint?: string;
}) {
  const [open, setOpen] = useState(false);
  const total = commentCount ?? comments.length;
  if (!total && comments.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-pink-500/40 hover:bg-pink-500/10"
      >
        <span>{open ? '▾' : '▸'}</span>
        {open ? 'Hide comments' : 'View comments'}
        <span className="text-slate-500">({formatCount(total)})</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {comments.length > 0 ? (
            comments.map((c, idx) => <CommentRow key={`${c.username}_${idx}`} comment={c} />)
          ) : (
            <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/90">
              {sessionHint || 'Comment text is not available for this post. Count shown above may still be accurate.'}
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
  const src = `https://www.instagram.com/${encodeURIComponent(username)}/embed/`;
  return (
    <iframe
      title={`Instagram @${username}`}
      src={src}
      className="w-full rounded-xl border border-pink-500/25 bg-black"
      style={{ minHeight: height }}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
    />
  );
}

function InstagramPostEmbed({ shortcode, url }: { shortcode?: string; url?: string }) {
  const code = extractIgShortcode(url, shortcode);
  if (!code) return null;
  return (
    <iframe
      title={`Instagram post ${code}`}
      src={`https://www.instagram.com/p/${encodeURIComponent(code)}/embed/captioned`}
      className="w-full rounded-lg border border-pink-500/20 bg-black"
      style={{ minHeight: 420 }}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-presentation"
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
            <MediaPreview url={src} alt={`Photo ${idx + 1} of ${slides.length}`} openHref={openHref} />
          </div>
        ))}
      </div>
      <p className="border-t border-pink-500/10 px-2 py-1.5 text-center text-[11px] text-slate-500">
        {slides.length} photos in this post — swipe to view all
      </p>
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
  const preview = isReel ? videoSrc : postPreviewUrl(post as never);
  const visit = externalVisitUrl(pickMediaUrl(post.live_url as string, post.url as string));
  const shortcode = extractIgShortcode(visit, post.shortcode as string | undefined);
  const media = (post.media as Record<string, unknown>[] | undefined) ?? [];
  const isCarousel = !isReel && (media.length > 1 || post.type === 'Carousel');
  const comments = normalizeComments(post.comments);
  const engagement = postEngagement(post);
  const hashtags = (post.hashtags as string[] | undefined) ?? [];
  const mentions = (post.mentions as string[] | undefined) ?? [];
  const showEmbed = !preview && !isCarousel && Boolean(shortcode);

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
        ) : (
          <MediaPreview url={preview} alt={String(post.caption || 'Instagram post')} isVideo={isReel} posterUrl={poster} openHref={visit} />
        )}
        <EngagementBar likes={engagement.likes} views={engagement.views} comments={engagement.comments} duration={engagement.duration} />
        {post.caption != null && String(post.caption) && (
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{String(post.caption)}</p>
        )}
        {hashtags.length > 0 && <p className="mt-2 text-xs text-pink-300/80">{hashtags.map((h) => `#${h}`).join(' ')}</p>}
        {mentions.length > 0 && <p className="mt-1 text-xs text-slate-400">Mentions: {mentions.map((m) => `@${m}`).join(', ')}</p>}
        <CommentsPanel comments={comments} commentCount={engagement.comments} sessionHint={sessionHint} />
        {visit && (
          <a href={externalVisitUrl(visit) || visit} target="_blank" rel="noreferrer noopener" className="mt-3 inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-xs font-semibold text-pink-200 hover:bg-pink-500/20">
            Open on Instagram ↗
          </a>
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

      {username && usePublicEmbed && !hasServerMedia && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-pink-400">Profile & recent posts</h4>
          <InstagramEmbedFrame username={username} height={520} />
        </div>
      )}

      {(posts.length > 0 || reels.length > 0) && (
        <div className="space-y-6 rounded-xl border border-pink-500/25 bg-pink-950/10 p-4">
          <SamuraiSectionHeader
            title={`@${username || 'target'} — profile posts`}
            subtitle="Target account media loaded in-app"
            accent="pink"
          />
          {reels.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Reels & videos ({reels.length})
              </h5>
              <div className="grid gap-4 md:grid-cols-2">
                {reels.map((post, idx) => (
                  <IgPostCard key={String(post.shortcode || post.url || idx)} post={post} index={idx} sessionHint={sessionHint} />
                ))}
              </div>
            </div>
          )}
          {posts.length > 0 && (
            <div className="space-y-3">
              <h5 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Recent posts ({posts.length})
              </h5>
              <div className="grid gap-4 md:grid-cols-2">
                {posts.map((post, idx) => (
                  <IgPostCard key={String(post.shortcode || post.url || idx)} post={post} index={idx} sessionHint={sessionHint} />
                ))}
              </div>
            </div>
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
