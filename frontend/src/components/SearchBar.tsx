import { useRef, useState, useEffect, useMemo } from 'react';
import { startInvestigation, stopInvestigation, loadInvestigationById } from '../api/investigate';
import { uploadImage } from '../api/client';
import { useInvestigationStore } from '../store/investigationStore';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';
import { IntelSelect } from './ui/IntelSelect';
import { Spinner } from './loading';
import type { QueryType } from '../types';

const QUERY_TYPES: { value: QueryType; label: string; icon: string }[] = [
  { value: 'auto', label: 'Auto detect', icon: '✦' },
  { value: 'username', label: 'Username', icon: '@' },
  { value: 'email', label: 'Email', icon: '✉' },
  { value: 'phone', label: 'Phone number', icon: '📱' },
  { value: 'domain', label: 'Domain', icon: '🌐' },
  { value: 'image', label: 'Image', icon: '🖼' },
];

type SpeedMode = 'standard' | 'fast' | 'samurai' | 'deep';

const SPEED_OPTIONS: { value: SpeedMode; label: string; hint: string; icon: string; imageOnly?: boolean }[] = [
  { value: 'standard', label: 'Standard', hint: '~5 min · balanced collection', icon: '⚡' },
  { value: 'fast', label: 'Quick', hint: '~2 min · seed only, no expansion', icon: '🚀' },
  { value: 'samurai', label: 'Social (Samurai)', hint: '~2 min · Instagram & Facebook', icon: '📲' },
  { value: 'deep', label: 'Deep', hint: '10+ min · up to 20 expansion hops', icon: '🔬' },
];

const ACCEPTED_IMAGE_TYPES = 'image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp';

interface CaseInvestigationRef {
  investigation_id: string;
  query: string;
  created_at?: string;
}

interface SearchBarProps {
  caseInvestigations?: CaseInvestigationRef[];
  investigationsLoading?: boolean;
}

function guessQueryIcon(query: string): string {
  if (/^[\d+\-\s()]{8,}$/.test(query.replace(/\s/g, ''))) return '📱';
  if (query.includes('@')) return '✉';
  if (query.startsWith('http')) return '🖼';
  return '◎';
}

function formatRecentDate(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso.slice(0, 10);
  }
}

export function SearchBar({ caseInvestigations, investigationsLoading = false }: SearchBarProps = {}) {
  const [input, setInput] = useState('');
  const [queryType, setQueryType] = useState<QueryType>('auto');
  const [speedMode, setSpeedMode] = useState<SpeedMode>('standard');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const status = useInvestigationStore((s) => s.status);
  const reset = useInvestigationStore((s) => s.reset);
  const recentGlobal = useInvestigationStore((s) => s.recentInvestigations);
  const activeCaseId = useAuthStore((s) => s.activeCaseId);
  const setError = useInvestigationStore((s) => s.setError);
  const setUploadedImage = useInvestigationStore((s) => s.setUploadedImage);
  const prefillSearch = useUiStore((s) => s.prefillSearch);
  const setPrefillSearch = useUiStore((s) => s.setPrefillSearch);

  useEffect(() => {
    if (prefillSearch) {
      setInput(prefillSearch);
      setPrefillSearch(null);
    }
  }, [prefillSearch, setPrefillSearch]);

  const isImageMode = queryType === 'image';
  const canStart = isImageMode ? !!selectedFile || !!input.trim() : !!input.trim();
  const textPlaceholder = isImageMode
    ? 'Or paste image URL (optional if file selected)…'
    : 'Username, email, phone, domain, or combo: johndoe | johndoe@example.com';

  const speedOptions = SPEED_OPTIONS.filter((o) => !o.imageOnly);

  const recent = useMemo(() => {
    let items: { id: string; query: string; queryType: string; completedAt: string }[] = [];
    if (caseInvestigations?.length) {
      items = caseInvestigations.map((inv) => ({
        id: inv.investigation_id,
        query: inv.query,
        queryType: 'auto',
        completedAt: inv.created_at || '',
      }));
    } else if (activeCaseId) {
      items = recentGlobal.filter((r) => r.caseId === activeCaseId);
    }
    const seen = new Set<string>();
    return items.filter((r) => {
      if (seen.has(r.id)) return false;
      seen.add(r.id);
      return true;
    });
  }, [caseInvestigations, activeCaseId, recentGlobal]);

  const clearFileSelection = () => {
    setSelectedFile(null);
    if (localPreview) URL.revokeObjectURL(localPreview);
    setLocalPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileChange = (file: File | null) => {
    if (localPreview) URL.revokeObjectURL(localPreview);
    setLocalPreview(null);
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/') && !/\.(jpe?g|png|gif|webp)$/i.test(file.name)) {
      setError('Please select a JPG, PNG, GIF, or WebP image.');
      return;
    }
    setSelectedFile(file);
    setLocalPreview(URL.createObjectURL(file));
    setQueryType('image');
    setInput('');
    setSpeedMode('standard');
  };

  const handleStart = async () => {
    if (!canStart || status === 'running' || uploading) return;

    const caseId = useAuthStore.getState().activeCaseId;
    const enterpriseAuth = useAuthStore.getState().enterpriseAuth;
    if (enterpriseAuth && !caseId) {
      setError('Select a case first — every investigation must belong to a case.');
      return;
    }

    const fastMode = speedMode === 'fast';
    const deepMode = speedMode === 'deep';
    const samuraiMode = speedMode === 'samurai';

    if (isImageMode && selectedFile) {
      setUploading(true);
      useInvestigationStore.setState({ error: null });
      try {
        const uploaded = await uploadImage(selectedFile);
        setUploadedImage(uploaded.preview_url, uploaded.filename);
        useInvestigationStore.getState().setQuery(uploaded.filename);
        startInvestigation(uploaded.image_path, 'image', 90, { fastMode, deepMode, samuraiMode });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Image upload failed');
      } finally {
        setUploading(false);
      }
      return;
    }

    const q = input.trim();
    if (!q) return;
    setUploadedImage(null, null);
    useInvestigationStore.getState().setQuery(q);
    const timeout = isImageMode ? 90 : 180;
    startInvestigation(q, isImageMode ? 'image' : queryType, timeout, { fastMode, deepMode, samuraiMode });
  };

  const handleClear = () => {
    setInput('');
    clearFileSelection();
    setUploadedImage(null, null);
    reset();
  };

  const handleRecent = async (id: string) => {
    if (!id || loadingRecent) return;
    setLoadingRecent(true);
    try {
      await loadInvestigationById(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoadingRecent(false);
    }
  };

  const queryTypeOptions = QUERY_TYPES.map((t) => ({
    value: t.value,
    label: t.label,
    icon: <span>{t.icon}</span>,
  }));

  const speedSelectOptions = speedOptions.map((o) => ({
    value: o.value,
    label: o.label,
    hint: o.hint,
    icon: <span>{o.icon}</span>,
    disabled: o.value === 'samurai' && isImageMode,
  }));

  const recentOptions = recent.map((r) => ({
    value: r.id,
    label: r.query,
    hint: formatRecentDate(r.completedAt) || r.queryType,
    icon: <span>{guessQueryIcon(r.query)}</span>,
  }));

  return (
    <div className="intel-panel p-5">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-slate-100">New Investigation</h2>
          <p className="mt-0.5 text-xs text-slate-500">Enter a target and configure collection settings</p>
        </div>
        <div className="flex items-center gap-2">
          {investigationsLoading && (
            <span className="flex items-center gap-2 text-xs text-slate-500">
              <Spinner size="sm" variant="dots" />
              Loading history…
            </span>
          )}
          {!investigationsLoading && recent.length > 0 && (
            <div className="relative min-w-[220px]">
              {loadingRecent && (
                <span className="pointer-events-none absolute right-10 top-1/2 z-10 -translate-y-1/2">
                  <Spinner size="sm" variant="ring" />
                </span>
              )}
              <IntelSelect
                value=""
                placeholder="Recent investigations"
                options={recentOptions}
                onChange={handleRecent}
                disabled={loadingRecent || status === 'running'}
                size="sm"
                align="right"
                maxMenuHeight={320}
              />
            </div>
          )}
        </div>
      </div>

      <div className="mb-5 grid gap-4 sm:grid-cols-2">
        <IntelSelect
          id="investigation-type"
          label="Investigation type"
          value={queryType}
          options={queryTypeOptions}
          disabled={status === 'running'}
          onChange={(next) => {
            setQueryType(next);
            if (next !== 'image') clearFileSelection();
            if (next === 'image') setSpeedMode('standard');
          }}
        />

        <IntelSelect
          id="investigation-speed"
          label="Investigation speed"
          value={speedMode}
          options={speedSelectOptions}
          disabled={status === 'running' || isImageMode}
          onChange={setSpeedMode}
        />
      </div>

      {isImageMode && (
        <>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Upload image</p>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_IMAGE_TYPES}
            className="hidden"
            disabled={status === 'running' || uploading}
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            disabled={status === 'running' || uploading}
            onClick={() => fileInputRef.current?.click()}
            className="mb-4 w-full rounded-xl border-2 border-dashed border-violet-500/25 bg-violet-500/5 px-4 py-8 text-center transition hover:border-violet-400/40 hover:bg-violet-500/10"
          >
            {localPreview ? (
              <div className="flex flex-col items-center gap-3">
                <img
                  src={localPreview}
                  alt="Selected"
                  className="max-h-40 max-w-full rounded-lg border border-slate-700 object-contain"
                />
                <p className="text-sm font-medium text-violet-200">{selectedFile?.name ?? 'Selected image'}</p>
                <p className="text-xs text-slate-500">Click to choose a different image</p>
              </div>
            ) : (
              <div>
                <p className="text-2xl">📁</p>
                <p className="mt-2 text-sm font-medium text-violet-200">Click to upload image</p>
                <p className="mt-1 text-xs text-slate-500">JPG, PNG, GIF, or WebP</p>
              </div>
            )}
          </button>
        </>
      )}

      <label htmlFor="investigation-target" className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {isImageMode ? 'Or paste image URL' : 'Investigation target'}
      </label>
      <input
        id="investigation-target"
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleStart()}
        placeholder={textPlaceholder}
        className="intel-input mb-4 w-full font-mono"
        disabled={status === 'running' || uploading}
      />

      <div className="flex flex-wrap gap-2">
        <button
          onClick={status === 'running' ? () => stopInvestigation() : handleStart}
          disabled={status === 'running' ? false : !canStart || uploading}
          className={status === 'running' ? 'intel-btn-ghost whitespace-nowrap border-rose-500/40 text-rose-300' : 'intel-btn-primary whitespace-nowrap'}
        >
          {uploading ? (
            <span className="flex items-center gap-2">
              <Spinner size="sm" variant="dots" />
              Uploading…
            </span>
          ) : status === 'running' ? (
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-rose-400" />
              Stop investigation
            </span>
          ) : (
            'Start investigation'
          )}
        </button>
        <button onClick={handleClear} disabled={status === 'running' || uploading} className="intel-btn-ghost">
          Clear
        </button>
        {isImageMode && selectedFile && (
          <button
            type="button"
            onClick={clearFileSelection}
            disabled={status === 'running' || uploading}
            className="intel-btn-ghost text-rose-300"
          >
            Remove image
          </button>
        )}
      </div>
    </div>
  );
}
