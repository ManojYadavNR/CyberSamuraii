import { apiAssetUrl } from '../api/client';
import type { AuthUser } from '../store/authStore';

function initialsFor(user: Pick<AuthUser, 'name' | 'username'>): string {
  const base = (user.name || user.username || 'U').trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

interface UserAvatarProps {
  user: Pick<AuthUser, 'name' | 'username' | 'avatar_url'>;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZE_CLASS = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-14 w-14 text-base',
};

export function UserAvatar({ user, size = 'sm', className = '' }: UserAvatarProps) {
  const src = apiAssetUrl(user.avatar_url);
  const sizeClass = SIZE_CLASS[size];

  if (src) {
    return (
      <img
        src={src}
        alt={user.name || user.username}
        className={`shrink-0 rounded-full object-cover ring-2 ring-cyan-500/25 ${sizeClass} ${className}`}
      />
    );
  }

  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500 to-blue-700 font-bold text-white shadow-inner shadow-cyan-900/40 ${sizeClass} ${className}`}
    >
      {initialsFor(user)}
    </div>
  );
}
