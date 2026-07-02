import { useEffect, useRef, useState } from 'react';
import { LuCamera, LuChevronDown, LuKeyRound, LuLogOut } from 'react-icons/lu';
import { logoutSession } from '../api/auth';
import { uploadProfileAvatar } from '../api/enterprise';
import { UserAvatar } from './UserAvatar';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import type { AuthUser } from '../store/authStore';

export function UserProfileMenu({ user }: { user: AuthUser }) {
  const setPage = useUiStore((s) => s.setPage);
  const updateUserProfile = useAuthStore((s) => s.updateUserProfile);
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const handlePhotoPick = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      const updated = await uploadProfileAvatar(file);
      const bust = updated.avatar_url
        ? `${updated.avatar_url}${updated.avatar_url.includes('?') ? '&' : '?'}t=${Date.now()}`
        : undefined;
      updateUserProfile({ ...updated, avatar_url: bust });
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div ref={rootRef} className="profile-menu">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`profile-menu__trigger ${open ? 'profile-menu__trigger--open' : ''}`}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <UserAvatar user={user} size="sm" />
        <div className="hidden min-w-0 text-left sm:block">
          <p className="truncate text-xs font-semibold text-slate-100">{user.name || user.username}</p>
          <p className="truncate text-[10px] font-medium uppercase tracking-wide text-cyan-400/90">
            {user.role}{user.department ? ` · ${user.department}` : ''}
          </p>
        </div>
        <LuChevronDown className={`profile-menu__chevron ${open ? 'profile-menu__chevron--open' : ''}`} aria-hidden />
      </button>

      {open && (
        <div role="menu" className="profile-menu__dropdown">
          <div className="profile-menu__hero">
            <button
              type="button"
              className="profile-menu__avatar-btn"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              title="Change profile photo"
            >
              <UserAvatar user={user} size="lg" />
              <span className="profile-menu__avatar-overlay">
                <LuCamera className="h-4 w-4" aria-hidden />
              </span>
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-white">{user.name || user.username}</p>
              <p className="truncate text-xs text-slate-400">@{user.username}</p>
              <span className="profile-menu__role-badge">
                {user.role.replace(/_/g, ' ')}{user.department ? ` · ${user.department}` : ''}
              </span>
            </div>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => void handlePhotoPick(e.target.files?.[0] || null)}
          />

          <div className="profile-menu__actions">
            <button
              type="button"
              role="menuitem"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="profile-menu__action"
            >
              <LuCamera className="profile-menu__action-icon profile-menu__action-icon--cyan" aria-hidden />
              <span>{uploading ? 'Uploading photo…' : 'Change profile photo'}</span>
            </button>
            {uploadError && <p className="profile-menu__error">{uploadError}</p>}
            <button
              type="button"
              role="menuitem"
              onClick={() => { setOpen(false); setPage('change-password'); }}
              className="profile-menu__action"
            >
              <LuKeyRound className="profile-menu__action-icon" aria-hidden />
              <span>Change password</span>
            </button>
            <div className="profile-menu__divider" />
            <button
              type="button"
              role="menuitem"
              onClick={() => { setOpen(false); void logoutSession(); }}
              className="profile-menu__action profile-menu__action--danger"
            >
              <LuLogOut className="profile-menu__action-icon" aria-hidden />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
