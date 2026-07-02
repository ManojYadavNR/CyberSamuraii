import { useMemo, useState } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import { resolveMediaUrl, resolveVideoUrl } from '../lib/mediaUrl';
import {
  formatCount,
  isVideoUrl,
  mediaEngagement,
  normalizeComments,
  pickMediaUrl,
  postEngagement,
  postPreviewUrl,
  resolveFbBiography,
  resolveIgBiography,
  samuraiIntelFromResult,
  type SamuraiComment,
} from '../lib/samuraiIntelView';
import {
  badgeForValue,
  isRecordVideo,
  mediaPreviewFromRecord,
  posterFromPost,
  posterFromRecord,
  SamuraiLinksRow,
  SamuraiValue,
  videoSourceFromPost,
  videoSourceFromRecord,
} from '../lib/samuraiDataRender';
import { CollapsibleSection } from './CollapsibleSection';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

function MediaPreview({
  url,
  alt,
  isVideo,
  posterUrl,
  openHref,
}: {
  url?: string;
  alt: string;
  isVideo?: boolean;
  posterUrl?: string;
  openHref?: string;
}) {
  const [failed, setFailed] = useState(false);
  const imageSrc = resolveMediaUrl(posterUrl || (!isVideo ? url : undefined));
  const videoSrc = resolveVideoUrl(isVideo ? url : undefined);
  const video = isVideo && Boolean(videoSrc);

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
        className="max-h-96 w-full rounded-lg border border-slate-700 bg-slate-950 object-contain"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <div className="flex aspect-video max-h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 bg-slate-950/60 px-4 text-center text-xs text-slate-500">
      <span>Preview unavailable in-app</span>
      {openHref && (
        <a href={openHref} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">
          {openHref.includes('facebook') ? 'Open on Facebook ↗' : 'Open on Instagram ↗'}
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

function SimilarProfileCard({ entry }: { entry: Record<string, unknown> }) {
  const avatar = resolveMediaUrl(entry.profile_pic_url as string);
  const photos = (entry.photos as Record<string, unknown>[] | undefined) ?? [];
  const profileUrl = pickMediaUrl(entry.profile_url as string);

  return (
    <article className="overflow-hidden rounded-xl border border-amber-500/25 bg-amber-500/5">
      <div className="flex items-start gap-3 p-3">
        {avatar ? (
          <img src={avatar} alt="" className="h-14 w-14 shrink-0 rounded-full border border-amber-400/30 object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-dashed border-amber-500/30 bg-slate-950 text-lg text-amber-400/60">
            ?
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-white">{String(entry.full_name || entry.username || 'Similar profile')}</p>
          {entry.username != null && <p className="font-mono text-xs text-amber-200/80">{String(entry.username)}</p>}
          {entry.photo_count != null && <p className="mt-1 text-[11px] text-slate-500">{Number(entry.photo_count)} photo(s) linked</p>}
          {profileUrl && (
            <a href={profileUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/20">
              Open on Facebook ↗
            </a>
          )}
        </div>
      </div>
      {photos.length > 0 && (
        <div className="grid grid-cols-3 gap-1 border-t border-amber-500/15 p-2">
          {photos.slice(0, 6).map((photo, idx) => {
            const src = resolveMediaUrl(mediaPreviewFromRecord(photo));
            if (!src) return null;
            return (
              <img key={idx} src={src} alt="" className="aspect-square rounded object-cover" loading="lazy" referrerPolicy="no-referrer" />
            );
          })}
        </div>
      )}
    </article>
  );
}

function PostFieldGrid({ data }: { data: Record<string, unknown> }) {
  const skip = new Set([
    'caption', 'comments', 'media', 'hashtags', 'mentions', 'video',
    'url', 'live_url', 'display_url', 'display_live_url', 'video_url', 'video_live_url',
    'thumbnail', 'thumbnail_live_url', 'profile_pic_url',
  ]);
  const entries = Object.entries(data).filter(([k, v]) => !skip.has(k) && !(typeof v === 'string' && v.startsWith('http')));
  if (!entries.length) return null;
  return (
    <dl className="mt-3 grid gap-2 rounded border border-slate-800/60 bg-slate-950/30 p-2 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-[10px] uppercase text-slate-500">{key.replace(/_/g, ' ')}</dt>
          <dd className="mt-0.5 break-all text-xs text-slate-300">
            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
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
  const visit = pickMediaUrl(post.live_url as string, post.url as string);
  const media = (post.media as Record<string, unknown>[] | undefined) ?? [];
  const comments = normalizeComments(post.comments);
  const engagement = postEngagement(post);
  const hashtags = (post.hashtags as string[] | undefined) ?? [];
  const mentions = (post.mentions as string[] | undefined) ?? [];

  return (
    <article className="overflow-hidden rounded-xl border border-pink-500/20 bg-pink-500/5">
      <div className="p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="muted">#{index + 1}</Badge>
          <Badge variant={isReel ? 'info' : 'muted'}>{isReel ? 'Reel / Video' : String(post.type || 'Post')}</Badge>
          {post.shortcode != null && <Badge variant="muted">{String(post.shortcode)}</Badge>}
        </div>
        <MediaPreview url={preview} alt={String(post.caption || 'Instagram post')} isVideo={isReel} posterUrl={poster} openHref={visit} />
        <EngagementBar likes={engagement.likes} views={engagement.views} comments={engagement.comments} duration={engagement.duration} />
        {media.length > 1 && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {media.map((item, idx) => {
              const src = mediaPreviewFromRecord(item);
              if (!src) return null;
              return <MediaPreview key={idx} url={src} alt={`Media ${idx + 1}`} isVideo={isVideoUrl(src)} openHref={visit} />;
            })}
          </div>
        )}
        {post.caption != null && String(post.caption) && (
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{String(post.caption)}</p>
        )}
        {hashtags.length > 0 && <p className="mt-2 text-xs text-pink-300/80">{hashtags.map((h) => `#${h}`).join(' ')}</p>}
        {mentions.length > 0 && <p className="mt-1 text-xs text-slate-400">Mentions: {mentions.map((m) => `@${m}`).join(', ')}</p>}
        <CommentsPanel comments={comments} commentCount={engagement.comments} sessionHint={sessionHint} />
        <PostFieldGrid data={post} />
        {visit && (
          <a href={visit} target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-lg border border-pink-500/30 bg-pink-500/10 px-3 py-1.5 text-xs font-semibold text-pink-200 hover:bg-pink-500/20">
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
  label,
}: {
  item: Record<string, unknown>;
  index: number;
  label: string;
}) {
  const isVideo = isRecordVideo(item);
  const videoSrc = videoSourceFromRecord(item);
  const poster = posterFromRecord(item);
  const preview = isVideo ? videoSrc : mediaPreviewFromRecord(item);
  const visit = pickMediaUrl(item.live_url as string, item.url as string);
  const engagement = mediaEngagement(item);
  const comments = normalizeComments(item.comments);
  const caption = String(item.title || item.caption || item.text || '').trim();

  return (
    <article className="overflow-hidden rounded-xl border border-blue-500/20 bg-blue-500/5">
      <div className="p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="muted">#{index + 1}</Badge>
          <Badge variant="info">{label}</Badge>
          {item.type != null && <Badge variant="muted">{String(item.type)}</Badge>}
        </div>
        <MediaPreview url={preview} alt={caption || label} isVideo={isVideo} posterUrl={poster} openHref={visit} />
        <EngagementBar likes={engagement.likes} views={engagement.views} comments={engagement.comments} />
        {caption && <p className="mt-3 whitespace-pre-wrap text-sm text-slate-300">{caption}</p>}
        <CommentsPanel comments={comments} commentCount={engagement.comments} />
        <PostFieldGrid data={item} />
        {visit && (
          <a href={visit} target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-500/20">
            Open on Facebook ↗
          </a>
        )}
      </div>
    </article>
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

function PlatformExplorer({
  title,
  data,
  skipKeys = [],
}: {
  title: string;
  data: Record<string, unknown>;
  skipKeys?: string[];
}) {
  const skip = new Set(skipKeys);
  const entries = Object.entries(data).filter(([key]) => !skip.has(key));
  return (
    <div className="space-y-3">
      <CollapsibleSection
        title={`${title} — complete API response`}
        subtitle="Every field returned by Samurai for this platform"
        badge={`${entries.length} top-level keys`}
        defaultOpen={false}
      >
        <SamuraiValue value={data} />
      </CollapsibleSection>
      {entries.map(([key, value]) => (
        <CollapsibleSection
          key={key}
          title={key.replace(/_/g, ' ')}
          badge={badgeForValue(value)}
          defaultOpen={['profile', 'stats', 'notes', 'data_availability', 'investigation', 'personal_details'].includes(key)}
        >
          <SamuraiValue value={value} />
        </CollapsibleSection>
      ))}
    </div>
  );
}

function InstagramSection({ data }: { data: Record<string, unknown> }) {
  const profile = (data.profile as Record<string, unknown> | undefined) ?? {};
  const links = (data.links as Record<string, unknown> | undefined) ?? {};
  const notes = (data.notes as Record<string, unknown> | undefined) ?? {};
  const allPosts = (data.recent_posts as Record<string, unknown>[] | undefined) ?? [];
  const reels = (data.reels as Record<string, unknown>[] | undefined) ?? [];
  const posts = allPosts.filter(
    (post) => !post.is_video && post.type !== 'Reel' && post.type !== 'Video',
  );
  const apiResponse = data.api_response as Record<string, unknown> | undefined;
  const bio = resolveIgBiography(profile, apiResponse);
  const authenticated = data.authenticated === true;
  const sessionHint = String(
    notes.comment_text
    || notes.session_help
    || (authenticated ? '' : 'Add IG_SESSIONID to .env (or samurai/cookies.txt) and restart the backend for bio + comment text.'),
  );
  const avatar = resolveMediaUrl(profile.profile_pic_url as string);
  const externalUrl = String(profile.external_url || '').trim();

  return (
    <div className="space-y-4">
      {!authenticated && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
          <p className="font-semibold text-slate-200">Public Instagram mode</p>
          <p className="mt-1 text-xs text-slate-400">
            Showing public bio, counts, and embed comment snippets when available. Add{' '}
            <code className="text-slate-200">IG_SESSIONID</code> to <code className="text-slate-200">.env</code>{' '}
            for full comment threads and rich API data.
          </p>
        </div>
      )}

      {apiResponse && (
        <CollapsibleSection
          title="Instagram API — full response (data.user)"
          subtitle="Every field from web_profile_info — same structure as _ig_*.json"
          badge="api_response"
          defaultOpen={false}
        >
          <SamuraiValue value={apiResponse} />
        </CollapsibleSection>
      )}

      <div className="flex flex-wrap items-start gap-4 rounded-xl border border-pink-500/25 bg-gradient-to-r from-pink-950/30 to-slate-900/40 p-4">
        {avatar ? (
          <img src={avatar} alt="" className="h-20 w-20 rounded-full border-2 border-pink-400/40 object-cover" loading="lazy" referrerPolicy="no-referrer" />
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
          <div className="mt-3">
            <SamuraiLinksRow links={links} />
          </div>
        </div>
      </div>

      {reels.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-pink-400">Reels & videos ({reels.length})</h4>
          <div className="grid gap-4 md:grid-cols-2">
            {reels.map((post, idx) => (
              <IgPostCard key={String(post.shortcode || post.url || idx)} post={post} index={idx} sessionHint={sessionHint} />
            ))}
          </div>
        </div>
      )}

      {posts.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-pink-400">Recent posts ({posts.length})</h4>
          <div className="grid gap-4 md:grid-cols-2">
            {posts.map((post, idx) => (
              <IgPostCard key={String(post.shortcode || post.url || idx)} post={post} index={idx} sessionHint={sessionHint} />
            ))}
          </div>
        </div>
      )}

      <PlatformExplorer title="Instagram" data={data} skipKeys={apiResponse ? ['api_response'] : []} />
    </div>
  );
}

function FacebookSection({ data }: { data: Record<string, unknown> }) {
  const profile = (data.profile as Record<string, unknown> | undefined) ?? {};
  const personal = (data.personal_details as Record<string, unknown> | undefined) ?? {};
  const links = (data.links as Record<string, unknown> | undefined) ?? {};
  const photos = (data.photos as Record<string, unknown>[] | undefined) ?? [];
  const videos = (data.videos as Record<string, unknown>[] | undefined) ?? [];
  const reels = (data.reels as Record<string, unknown>[] | undefined) ?? [];
  const timeline = (data.timeline_posts as Record<string, unknown>[] | undefined) ?? [];
  const friends = (data.friends as Record<string, unknown>[] | undefined) ?? [];
  const similar = (data.similar_profiles as Record<string, unknown>[] | undefined) ?? [];
  const bio = resolveFbBiography(profile, personal);
  const targetSlug = String(profile.username || '').toLowerCase();
  const profilePhotos = (profile.photos as Record<string, unknown>[] | undefined) ?? [];
  const targetPhotos = profilePhotos.length > 0
    ? profilePhotos
    : photos.filter((p) => p.is_target_profile !== false && (
      !p.owner_username || String(p.owner_username).toLowerCase() === targetSlug
    ));
  const relatedPhotos = photos.filter((p) => !targetPhotos.includes(p));
  const avatar = resolveMediaUrl(
    pickMediaUrl(
      profile.profile_pic_url as string,
      links.profile_picture as string,
      targetPhotos[0]?.thumbnail as string,
      targetPhotos[0]?.url as string,
    ),
  );

  const mediaSections: Array<{ key: string; label: string; title: string; items: Record<string, unknown>[] }> = [
    { key: 'target_photos', label: 'Photo', title: `Target profile photos (${targetPhotos.length})`, items: targetPhotos },
    { key: 'related_photos', label: 'Related photo', title: `Related / similar-name photos (${relatedPhotos.length})`, items: relatedPhotos },
    { key: 'videos', label: 'Video', title: `Videos (${videos.length})`, items: videos },
    { key: 'reels', label: 'Reel', title: `Reels (${reels.length})`, items: reels },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-4 rounded-xl border border-blue-500/25 bg-gradient-to-r from-blue-950/30 to-slate-900/40 p-4">
        {avatar ? (
          <img src={avatar} alt="" className="h-20 w-20 rounded-full border-2 border-blue-400/40 object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="flex h-20 w-20 items-center justify-center rounded-full border border-dashed border-blue-400/30 bg-slate-950 text-2xl text-blue-400/50">📘</div>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-white">{String(profile.full_name || profile.username || 'Facebook')}</h3>
          {profile.username != null && <p className="font-mono text-sm text-blue-300">{String(profile.username)}</p>}
          <ProfileBio bio={bio} hint="Bio may be hidden for locked profiles without Facebook session." />
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
            {profile.like_count != null && <span>{Number(profile.like_count).toLocaleString()} likes</span>}
            {profile.friend_count != null && <span>{Number(profile.friend_count).toLocaleString()} friends</span>}
            {profile.talking_about_count != null && <span>{Number(profile.talking_about_count).toLocaleString()} talking about</span>}
          </div>
          <div className="mt-3">
            <SamuraiLinksRow links={links} />
          </div>
        </div>
      </div>

      {similar.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-amber-300">Similar profiles ({similar.length})</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            {similar.map((entry, idx) => (
              <SimilarProfileCard key={String(entry.username || idx)} entry={entry} />
            ))}
          </div>
        </div>
      )}

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

      {mediaSections.map(({ key, label, title, items }) => items.length > 0 && (
        <div key={key}>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-400">
            {title}
          </h4>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item, idx) => (
              <FbMediaCard key={`${key}_${idx}`} item={item} index={idx} label={label} />
            ))}
          </div>
        </div>
      ))}

      {timeline.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-400">Timeline posts ({timeline.length})</h4>
          <div className="grid gap-4 sm:grid-cols-2">
            {timeline.map((post, idx) => (
              <FbTimelineCard key={idx} post={post} index={idx} />
            ))}
          </div>
        </div>
      )}

      <PlatformExplorer title="Facebook" data={data} />
    </div>
  );
}

export function SamuraiSocialPanel() {
  const result = useInvestigationStore((s) => s.result);
  const intel = useMemo(() => samuraiIntelFromResult(result), [result]);

  if (!result || !intel) return null;

  const ig = intel.instagram as Record<string, unknown> | null | undefined;
  const fb = intel.facebook as Record<string, unknown> | null | undefined;

  if (!ig && !fb) {
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

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-gradient-to-r from-pink-950/40 via-slate-900 to-blue-950/40 px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-fuchsia-400/90">Samurai deep social intel</p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          Instagram & Facebook — @{intel.username || String(ig?.profile && (ig.profile as Record<string, unknown>).username) || String(fb?.profile && (fb.profile as Record<string, unknown>).username)}
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          All fields from the Samurai response are shown below — media previews plus every metadata section.
        </p>
        {(intel.facebook_resolution || (ig?.profile as Record<string, unknown> | undefined)?.full_name) && (
          <div className="mt-2 space-y-1 text-xs text-slate-500">
            {(ig?.profile as Record<string, unknown> | undefined)?.full_name && (
              <p>Display name: {String((ig?.profile as Record<string, unknown>).full_name)}</p>
            )}
            {intel.facebook_resolution && (
              <p className="text-blue-400/80">
                Facebook matched via {String(intel.facebook_resolution).replace(/_/g, ' ')}
                {intel.facebook_slug ? ` → @${intel.facebook_slug}` : ''}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="space-y-8 p-5">
        {ig && (
          <div>
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xl">📸</span>
              <h3 className="text-sm font-bold uppercase tracking-wider text-pink-300">Instagram</h3>
            </div>
            <InstagramSection data={ig} />
          </div>
        )}
        {intel.instagram_error && !ig && (
          <p className="text-sm text-amber-400">Instagram error: {intel.instagram_error}</p>
        )}

        {fb && (
          <div>
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xl">📘</span>
              <h3 className="text-sm font-bold uppercase tracking-wider text-blue-300">Facebook</h3>
            </div>
            <FacebookSection data={fb} />
          </div>
        )}
        {intel.facebook_error && !fb && (
          <p className="text-sm text-amber-400">Facebook error: {intel.facebook_error}</p>
        )}

        <CollapsibleSection title="Samurai run metadata" subtitle="Errors, seed query, resolution notes" badge="meta" defaultOpen={false}>
          <SamuraiValue
            value={{
              username: intel.username,
              seed_query: intel.seed_query,
              facebook_slug: intel.facebook_slug,
              facebook_resolution: intel.facebook_resolution,
              instagram_error: intel.instagram_error,
              facebook_error: intel.facebook_error,
              cross_platform: intel.cross_platform,
            }}
          />
        </CollapsibleSection>
      </div>
    </section>
  );
}
