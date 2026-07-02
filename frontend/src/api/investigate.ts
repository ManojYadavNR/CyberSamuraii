import { getWsUrl, fetchReviews, fetchInvestigation, apiFetch } from './client';
import type { InvestigationResult } from '../types';
import { phoneToolStatuses } from '../lib/phoneIntelView';
import { useInvestigationStore } from '../store/investigationStore';
import { useAuthStore } from '../store/authStore';

let activeWs: WebSocket | null = null;
let recoveryAborted = false;
let userStoppedInvestigation = false;

function looksLikePhoneQuery(query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed || trimmed.includes('@')) return false;
  const digits = trimmed.replace(/[^\d+]/g, '');
  return digits.length >= 8 && /^\+?[\d\s().-]{8,}$/.test(trimmed);
}

function recoveryPauseMessage(queryType: string, mode: string): string {
  if (queryType === 'image') {
    return 'Live updates paused — still processing your image on the server. Results will load automatically (often 5–15 min on CPU).';
  }
  if (queryType === 'phone' || queryType === 'infra') {
    return 'Live updates paused — phone OSINT still running on the server (carrier lookup + social registration checks can take a few minutes).';
  }
  if (queryType === 'email') {
    return 'Live updates paused — email investigation still running on the server. Polling for results…';
  }
  if (mode === 'deep') {
    return 'Live updates paused — deep investigation still running on the server. Polling for expansion results…';
  }
  return 'Live updates paused — investigation still running on the server. Polling for results…';
}

function recoveryRunningMessage(queryType: string): string {
  if (queryType === 'phone' || queryType === 'infra') {
    return 'Phone OSINT still running — carrier lookup and social platform checks in progress…';
  }
  if (queryType === 'image') {
    return 'Backend still processing your image — results will appear automatically when ready.';
  }
  if (queryType === 'email') {
    return 'Email investigation still running — gathering registrations and profiles…';
  }
  return 'Investigation still running on the server — results will appear when ready.';
}

async function loadReviewsForInvestigation(id: string) {
  try {
    const data = await fetchReviews(id);
    useInvestigationStore.getState().setReviews(data.reviews);
  } catch {
    /* reviews optional */
  }
}

async function tryRecoverInvestigation(
  investigationId: string,
  options?: { isImage?: boolean; isPhone?: boolean; mode?: 'standard' | 'fast' | 'deep' },
): Promise<boolean> {
  const store = useInvestigationStore.getState();
  let notFoundStreak = 0;
  const maxAttempts = options?.mode === 'deep'
    ? 180
    : options?.isImage
      ? 180
      : options?.isPhone
        ? 144
        : 72;
  const pollMs = 5000;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (recoveryAborted || useInvestigationStore.getState().status !== 'running') {
      return useInvestigationStore.getState().status === 'complete';
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
    try {
      const inv = await fetchInvestigation(investigationId);
      notFoundStreak = 0;
      if (inv.status === 'complete' && inv.result) {
        store.setComplete(inv.id, inv.result);
        store.addRecent({
          id: inv.id,
          query: useInvestigationStore.getState().query,
          queryType: useInvestigationStore.getState().queryType,
          completedAt: new Date().toISOString(),
          caseId: useAuthStore.getState().activeCaseId || undefined,
        });
        await loadReviewsForInvestigation(inv.id);
        return true;
      }
      if (inv.status === 'error') {
        store.setError(
          typeof inv.error === 'string' && inv.error
            ? inv.error
            : 'Investigation failed on the server. Wait a moment and try again.',
        );
        return false;
      }
      if (inv.status === 'running') {
        const qt = useInvestigationStore.getState().queryType;
        useInvestigationStore.setState({
          error: recoveryRunningMessage(qt),
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (message.includes('not found') || message.includes('404')) {
        notFoundStreak += 1;
        if (notFoundStreak >= 3) {
          const qt = useInvestigationStore.getState().queryType;
          useInvestigationStore.getState().setError(
            qt === 'image'
              ? 'Investigation not found on server (likely restarted mid-run). Please upload the image and start again.'
              : 'Investigation not found on server (backend may have restarted). Please run the search again.',
          );
          return false;
        }
      }
    }
  }
  return false;
}

export function stopInvestigation(): void {
  const store = useInvestigationStore.getState();
  if (store.status !== 'running') return;

  recoveryAborted = true;
  userStoppedInvestigation = true;

  if (activeWs) {
    try {
      if (activeWs.readyState === WebSocket.OPEN) {
        activeWs.send(JSON.stringify({ action: 'cancel' }));
      }
    } catch {
      /* ignore */
    }
    activeWs.onclose = null;
    activeWs.onerror = null;
    activeWs.onmessage = null;
    try {
      activeWs.close();
    } catch {
      /* ignore */
    }
    activeWs = null;
  }

  void apiFetch('/api/dashboard/investigate/cancel', { method: 'POST' }).catch(() => undefined);

  useInvestigationStore.setState({
    status: 'idle',
    phase: 'cancelled',
    error: 'Investigation stopped.',
  });
  window.setTimeout(() => {
    if (useInvestigationStore.getState().error === 'Investigation stopped.') {
      useInvestigationStore.setState({ error: null });
    }
    userStoppedInvestigation = false;
  }, 4000);
}

export function startInvestigation(
  query: string,
  queryType?: string,
  timeout = 180,
  options?: { fastMode?: boolean; deepMode?: boolean; samuraiMode?: boolean },
): void {
  const store = useInvestigationStore.getState();
  if (store.status === 'running') {
    store.setError('An investigation is already running. Wait for it to finish before starting another.');
    return;
  }
  recoveryAborted = false;
  userStoppedInvestigation = false;
  store.reset();
  store.setQuery(query);
  const resolvedType = queryType && queryType !== 'auto' ? queryType : 'auto';
  const isImage = resolvedType === 'image';
  const isPhone = resolvedType === 'phone' || resolvedType === 'infra'
    || (resolvedType === 'auto' && looksLikePhoneQuery(query));
  useInvestigationStore.setState({ queryType: isPhone && resolvedType === 'auto' ? 'phone' : resolvedType });
  store.setRunning();

  const isMultiInput = /[|;/\n]/.test(query) || (query.includes('@') && query.split(/\s+/).length > 1);
  const investigationMode = options?.samuraiMode
    ? 'samurai'
    : options?.deepMode
      ? 'deep'
      : options?.fastMode
        ? 'fast'
        : 'standard';
  useInvestigationStore.setState({ investigationMode });

  const discovery = investigationMode === 'samurai' || investigationMode === 'fast'
    ? { enabled: false }
    : investigationMode === 'deep'
    ? { enabled: true, max_depth: 4, max_hops: 20, max_leads_per_hop: 12, max_total_leads: 50 }
    : isPhone
      ? { enabled: false }
    : isImage && investigationMode === 'fast'
      ? { enabled: true, max_depth: 2, max_hops: 4, max_leads_per_hop: 4, max_total_leads: 8 }
      : isImage
        ? { enabled: true, max_depth: 2, max_hops: 6, max_leads_per_hop: 4, max_total_leads: 10 }
        : investigationMode === 'fast'
          ? { enabled: false }
          : !isImage
            ? { enabled: true, max_depth: 2, max_hops: 2, max_leads_per_hop: 5, max_total_leads: 12 }
            : undefined;

  const imageProfile = investigationMode === 'deep' ? 'deep' : 'fast';
  const timeoutPerTool = investigationMode === 'samurai'
    ? 360
    : investigationMode === 'deep'
    ? 300
    : isImage
      ? 40
      : isPhone
        ? 180
      : isMultiInput
        ? investigationMode === 'fast' ? 90 : 150
        : investigationMode === 'fast'
          ? 120
          : timeout;

  if (activeWs) {
    activeWs.onclose = null;
    activeWs.onerror = null;
    activeWs.close();
    activeWs = null;
  }

  const ws = new WebSocket(getWsUrl());
  activeWs = ws;
  let wsFinished = false;

  ws.onopen = () => {
    const { accessToken, activeCaseId } = useAuthStore.getState();
    ws.send(JSON.stringify({
      query,
      query_type: queryType === 'auto' ? undefined : queryType,
      timeout_per_tool: timeoutPerTool,
      investigation_mode: investigationMode,
      image_profile: isImage ? imageProfile : undefined,
      access_token: accessToken || undefined,
      case_id: activeCaseId || undefined,
      ...(discovery ? { discovery } : {}),
    }));
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const s = useInvestigationStore.getState();

    if (data.investigation_id) {
      useInvestigationStore.setState({ investigationId: data.investigation_id });
    }

    if (data.error) {
      if (data.status === 'busy') {
        s.setError(
          `${data.error} Only one investigation can run at a time — wait for the current scan to finish, then try again.`,
        );
        wsFinished = true;
        ws.close();
        return;
      }
      if (data.phase !== 'tool' && data.phase !== 'hop_failed' && (data.phase === 'error' || data.status === 'error')) {
        s.setError(data.error);
        wsFinished = true;
        ws.close();
        return;
      }
    }

    if (data.query_type) {
      useInvestigationStore.setState({ queryType: data.query_type });
    }

    if (data.investigation_mode) {
      useInvestigationStore.setState({ investigationMode: data.investigation_mode });
    }

    if (data.phase === 'heartbeat') {
      return;
    }

    if (data.phase === 'accepted' || data.phase === 'start') {
      if (data.investigation_mode) {
        useInvestigationStore.setState({ investigationMode: data.investigation_mode });
      }
      if (data.query_type) {
        useInvestigationStore.setState({ queryType: data.query_type });
      }
      if (data.phase === 'start') {
        s.setPhase('start');
      }
      if (data.phase === 'accepted') {
        return;
      }
    }

    if (data.phase === 'multi_input') {
      s.setPhase('multi_input');
      const branch = data.branch ? ` · ${data.branch}` : '';
      const mode = data.mode ? ` (${data.mode})` : '';
      const toolStatus =
        data.status === 'done' ? 'done'
        : data.status === 'warning' ? 'failed'
        : 'running';
      s.updateToolProgress('multi_input', {
        status: toolStatus,
        success: data.status === 'done' ? true : data.status === 'warning' ? false : undefined,
        detail: String(data.message || data.status || 'Multi-input scan') + mode + branch,
      });
    } else if (
      data.phase === 'fusion'
      || data.phase === 'evidence_extraction'
      || data.phase === 'correlation'
      || data.phase === 'graph'
    ) {
      s.setPhase(data.phase);
      if (data.status === 'running') {
        if (data.phase === 'fusion') {
          s.updateToolProgress('multi_input', { status: 'done', success: true });
        }
        s.updateToolProgress('post_processing', {
          status: 'running',
          detail: String(data.message || `${data.phase.replace(/_/g, ' ')}…`),
        });
      } else if (data.status === 'done') {
        s.updateToolProgress('post_processing', {
          status: 'done',
          success: true,
          detail: data.phase === 'graph'
            ? `Graph ready · ${data.nodes ?? 0} node(s)`
            : data.phase === 'correlation'
              ? `${data.clusters ?? 0} cluster(s)`
              : data.phase === 'evidence_extraction'
                ? `${data.platforms_analyzed ?? 0} platform(s) analyzed`
                : `Fusion score ${data.fusion_score ?? '—'}`,
        });
      }
    } else if (data.phase === 'tool') {
      if (data.status === 'running' || data.status === 'pending') {
        s.setPhase('tool');
      }
      const toolStatus =
        data.status === 'running' ? 'running'
        : data.status === 'pending' ? 'pending'
        : data.success ? 'done' : 'failed';
      s.updateToolProgress(data.tool, {
        status: toolStatus,
        success: data.success,
        execution_time_ms: data.execution_time_ms,
        error: data.tool_error ?? data.error,
      });
    } else if (data.phase === 'reverse_image_discovery') {
      s.setPhase('reverse_image_discovery');
      const running = data.status === 'running';
      const sources = Array.isArray(data.sources_run) ? data.sources_run.join(', ') : '';
      s.updateToolProgress('reverse_image_search', {
        status: running ? 'running' : 'done',
        success: !running,
        detail: running
          ? 'Uploading photo to Google Lens, Yandex, Bing + public search…'
          : `${data.matches ?? 0} visual match(es) · sources: ${sources || 'none'}`,
      });
    } else if (data.phase === 'image_intelligence' && data.status === 'running') {
      s.setPhase('image_intelligence');
      s.updateToolProgress('image_intelligence', {
        status: 'running',
        detail: 'Merging face, OCR, and fingerprint signals…',
      });
    } else if (data.phase === 'image_intelligence' && data.status === 'done') {
      s.setPhase('image_intelligence');
      s.updateToolProgress('image_intelligence', {
        status: 'done',
        success: true,
        detail: `${data.face_count ?? 0} face(s) · ${data.findings_count ?? 0} finding(s)`,
      });
    } else if (data.phase === 'finding_discovered') {
      s.addLiveFinding({
        type: String(data.finding_type || 'finding'),
        value: String(data.value || ''),
        confidence: data.confidence,
        source: data.source || data.platform,
      });
    } else if (data.phase === 'collection_partial') {
      s.setPhase('tool');
      const query = useInvestigationStore.getState().query;
      s.setPartialResult(
        {
          fusion: data.fusion,
          identity_profile: data.identity_profile,
          evidence_extraction: data.evidence_extraction,
          correlation: data.correlation,
          graph: data.graph,
          tool_results: data.tool_results,
        },
        {
          scanPhase: data.scan_phase,
          sitesChecked: data.sites_checked,
          sitesTotal: data.sites_total,
        },
      );
      if (Array.isArray(data.tool_results) && data.tool_results.length > 0) {
        const partialResult = {
          feature: useInvestigationStore.getState().result?.feature ?? 'infra_intel',
          query,
          tool_results: data.tool_results,
        } as InvestigationResult;
        for (const toolStatus of phoneToolStatuses(partialResult)) {
          if (toolStatus.detail) {
            s.updateToolProgress(toolStatus.tool, { detail: toolStatus.detail });
          }
        }
      }
    } else if (data.phase === 'scan_progress') {
      s.setPhase('tool');
      s.updateToolProgress(String(data.tool), {
        status: 'running',
        detail: `Phase ${data.scan_phase}: ${data.sites_checked ?? 0}/${data.sites_total ?? '?'} sites · ${data.hits ?? 0} hit(s)`,
      });
      if (typeof data.sites_checked === 'number') {
        useInvestigationStore.setState({
          scanPhase: data.scan_phase ?? useInvestigationStore.getState().scanPhase,
          sitesChecked: data.sites_checked,
          sitesTotal: data.sites_total ?? useInvestigationStore.getState().sitesTotal,
        });
      }
    } else if (data.phase === 'fusion_partial') {
      s.setPhase('tool');
      if (data.latest_tool) {
        s.updateToolProgress(String(data.latest_tool), {
          detail: `Stage 1 · ${data.tools_done}/${data.tools_total} modules`,
        });
      }
    } else if (data.phase === 'profile_partial') {
      s.setPhase('discovery');
    } else if (data.phase === 'profile_verification') {
      s.setPhase('profile_verification');
    } else if (data.phase === 'discovery' || data.phase === 'hop_started' || data.phase === 'hop_completed' || data.phase === 'hop_failed') {
      s.setPhase('discovery');
      if (data.phase === 'hop_started') {
        s.updateToolProgress(`hop:${data.query ?? data.hop_id}`, { status: 'running' });
      } else if (data.phase === 'hop_completed') {
        s.updateToolProgress(`hop:${data.query ?? data.hop_id}`, { status: 'done', success: true });
      } else if (data.phase === 'hop_failed') {
        s.updateToolProgress(`hop:${data.query ?? data.hop_id}`, { status: 'failed', error: data.error });
      }
    } else if (data.phase) {
      s.setPhase(data.phase);
    }

    if (data.phase === 'cancelled' || data.status === 'cancelled') {
      wsFinished = true;
      ws.close();
      s.setError(data.error || 'Investigation stopped.');
      useInvestigationStore.setState({ status: 'idle', phase: 'cancelled' });
      return;
    }

    if (data.phase === 'finished' || data.phase === 'complete') {
      const result = data.result as InvestigationResult;
      s.setComplete(data.investigation_id, result);
      useInvestigationStore.getState().addRecent({
        id: data.investigation_id,
        query: useInvestigationStore.getState().query,
        queryType: useInvestigationStore.getState().queryType,
        completedAt: new Date().toISOString(),
        caseId: useAuthStore.getState().activeCaseId || undefined,
      });
      loadReviewsForInvestigation(data.investigation_id);
      wsFinished = true;
      ws.close();
    }
  };

  ws.onerror = () => {
    if (!wsFinished) {
      useInvestigationStore.getState().setError('WebSocket connection failed. Is the backend running on port 8000?');
    }
  };

  ws.onclose = () => {
    if (activeWs !== ws) return;
    activeWs = null;
    if (wsFinished || userStoppedInvestigation) return;
    const s = useInvestigationStore.getState();
    if (s.status !== 'running') return;

    const investigationId = s.investigationId;
    if (investigationId) {
      const qt = s.queryType;
      const mode = s.investigationMode;
      useInvestigationStore.setState({
        error: recoveryPauseMessage(qt, mode),
      });
      void tryRecoverInvestigation(investigationId, {
        isImage: qt === 'image',
        isPhone: qt === 'phone' || qt === 'infra',
        mode: s.investigationMode,
      }).then((recovered) => {
        if (recovered) {
          useInvestigationStore.setState({ error: null });
          return;
        }
        const id = useInvestigationStore.getState().investigationId;
        if (useInvestigationStore.getState().status === 'running') {
          useInvestigationStore.getState().setError(
            id
              ? `Investigation did not finish in time. Check terminal logs, or load ID: ${id}`
              : 'Investigation connection closed before completion. Please try again.',
          );
        }
      });
      return;
    }

    s.setError('Investigation connection closed before completion. Please try again.');
  };
}

export async function loadInvestigationById(id: string): Promise<void> {
  const inv = await fetchInvestigation(id);
  if (!inv.result) throw new Error('Investigation has no result data');
  useInvestigationStore.getState().loadFromServer(inv.id, inv.query, inv.query_type, inv.result);
  await loadReviewsForInvestigation(id);
}
