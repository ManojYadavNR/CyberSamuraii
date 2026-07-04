import { getWsUrl, fetchReviews, fetchInvestigation, apiFetch } from './client';
import type { InvestigationResult } from '../types';
import { phoneToolStatuses } from '../lib/phoneIntelView';
import { toolFindingsCount } from '../lib/uiHelpers';
import { useInvestigationStore } from '../store/investigationStore';
import { useAuthStore } from '../store/authStore';

let activeWs: WebSocket | null = null;
let recoveryAborted = false;
let userStoppedInvestigation = false;
/** Bumped on every start/stop so stale recovery loops and late WS events are ignored. */
let investigationEpoch = 0;

function looksLikePhoneQuery(query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed || trimmed.includes('@')) return false;
  const digits = trimmed.replace(/[^\d+]/g, '');
  return digits.length >= 8 && /^\+?[\d\s().-]{8,}$/.test(trimmed);
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
  epoch: number,
  options?: { isImage?: boolean; isPhone?: boolean; mode?: 'standard' | 'fast' | 'deep' | 'samurai' },
): Promise<boolean> {
  const store = useInvestigationStore.getState();
  let notFoundStreak = 0;
  const maxAttempts = options?.mode === 'deep'
    ? 180
    : options?.mode === 'samurai'
      ? 60 // ~2.5 min poll window; Samurai wall is ~120s
    : options?.isImage
      ? 180
      : options?.isPhone
        ? 144
        : 72;
  const pollMs = options?.mode === 'samurai' ? 2500 : 5000;

  const isCurrent = () =>
    epoch === investigationEpoch
    && useInvestigationStore.getState().investigationId === investigationId
    && useInvestigationStore.getState().status === 'running';

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (recoveryAborted || !isCurrent()) {
      return useInvestigationStore.getState().status === 'complete';
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
    if (!isCurrent()) {
      return useInvestigationStore.getState().status === 'complete';
    }
    try {
      const inv = await fetchInvestigation(investigationId);
      if (!isCurrent()) {
        return useInvestigationStore.getState().status === 'complete';
      }
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
      if (inv.status === 'error' || inv.status === 'cancelled') {
        // Prefer any partial result already on disk over a blank error screen.
        if (inv.result && (inv.result as InvestigationResult).tool_results?.length) {
          store.setComplete(inv.id, inv.result as InvestigationResult);
          return true;
        }
        store.setError(
          typeof inv.error === 'string' && inv.error
            ? inv.error
            : 'Investigation failed on the server. Wait a moment and try again.',
        );
        return false;
      }
      // status === running with partial result: paint UI immediately, keep polling for complete.
      if (inv.status === 'running' && inv.result) {
        store.setPartialResult(inv.result as Partial<InvestigationResult>);
        const mode = useInvestigationStore.getState().investigationMode;
        const partial = inv.result as InvestigationResult;
        const hasSamurai = partial.tool_results?.some((t) => t.tool === 'samurai' && t.success)
          || Boolean(partial.evidence_extraction?.samurai_social_intel);
        if (mode === 'samurai' && hasSamurai) {
          store.setComplete(inv.id, partial);
          await loadReviewsForInvestigation(inv.id);
          return true;
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (message.includes('not found') || message.includes('404')) {
        notFoundStreak += 1;
        if (notFoundStreak >= 3) {
          if (!isCurrent()) return false;
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

  investigationEpoch += 1;
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
  // Invalidate any in-flight recovery / late WS handlers from prior runs.
  investigationEpoch += 1;
  const epoch = investigationEpoch;
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
    : isImage
      ? { enabled: true, max_depth: 2, max_hops: 6, max_leads_per_hop: 4, max_total_leads: 10 }
      : { enabled: true, max_depth: 2, max_hops: 2, max_leads_per_hop: 5, max_total_leads: 12 };

  const imageProfile = investigationMode === 'deep' ? 'deep' : 'fast';
  const timeoutPerTool = investigationMode === 'samurai'
    ? 130
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
    // Ignore late events from a previous investigation after stop/restart/complete.
    if (epoch !== investigationEpoch) return;

    const data = JSON.parse(event.data);
    const s = useInvestigationStore.getState();

    // Once complete, ignore everything except a matching finished payload.
    if (s.status === 'complete') {
      if (
        (data.phase === 'finished' || data.phase === 'complete')
        && data.result
        && data.investigation_id === s.investigationId
      ) {
        s.setComplete(data.investigation_id, data.result as InvestigationResult);
      }
      return;
    }

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
      const findingsCount = typeof data.findings_count === 'number' ? data.findings_count : undefined;
      s.updateToolProgress(data.tool, {
        status: toolStatus,
        success: data.success,
        execution_time_ms: data.execution_time_ms,
        error: data.tool_error ?? data.error,
        ...(data.detail ? { detail: String(data.detail) } : {}),
        ...(findingsCount != null ? { findings_count: findingsCount } : {}),
      });

      // Samurai ships tool_result + intel on tool-done — apply immediately so the
      // Intelligence panel is not empty while post-processing / WS finish races.
      if (
        data.tool === 'samurai'
        && (data.status === 'done' || data.success)
        && (data.tool_result || data.samurai_social_intel || data.evidence_extraction)
      ) {
        const existing = useInvestigationStore.getState().result;
        const toolResults = data.tool_result
          ? [data.tool_result]
          : (existing?.tool_results ?? []);
        const evidenceExtraction = data.evidence_extraction
          ?? (data.samurai_social_intel
            ? {
                ...(existing?.evidence_extraction ?? {}),
                samurai_social_intel: data.samurai_social_intel,
              }
            : existing?.evidence_extraction);
        const partial = {
          feature: existing?.feature ?? 'username_search',
          query: useInvestigationStore.getState().query,
          tool_results: toolResults,
          evidence_extraction: evidenceExtraction,
          fusion: existing?.fusion ?? data.fusion,
        } as InvestigationResult;
        s.setPartialResult(partial);
        // Samurai mode is single-tool — mark complete as soon as intel arrives.
        if (
          useInvestigationStore.getState().investigationMode === 'samurai'
          && data.success
          && data.investigation_id
        ) {
          const painted = useInvestigationStore.getState().result ?? partial;
          s.setComplete(data.investigation_id, painted);
        }
      }
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
      const partialPayload = {
        fusion: data.fusion,
        identity_profile: data.identity_profile,
        evidence_extraction: data.evidence_extraction,
        correlation: data.correlation,
        graph: data.graph,
        tool_results: data.tool_results,
        confirmed_findings: data.confirmed_findings,
        public_profile_data: data.public_profile_data,
        investigation_leads: data.investigation_leads,
        scan_summary: data.scan_summary,
      };
      // If Samurai already marked complete, still merge richer partial data.
      if (useInvestigationStore.getState().status === 'complete') {
        s.updateResult(partialPayload);
      } else {
        s.setPartialResult(partialPayload, {
          scanPhase: data.scan_phase,
          sitesChecked: data.sites_checked,
          sitesTotal: data.sites_total,
        });
      }
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
        const samuraiTr = data.tool_results.find(
          (t: { tool?: string; success?: boolean; raw_output?: string }) => t.tool === 'samurai' && t.success,
        );
        if (samuraiTr) {
          const n = toolFindingsCount(
            { tool_results: data.tool_results, query, feature: 'username_search' } as InvestigationResult,
            'samurai',
          );
          s.updateToolProgress('samurai', {
            status: 'done',
            success: true,
            findings_count: n,
            detail: samuraiTr.raw_output || 'Samurai collection complete',
          });
        }
      }
      if (
        useInvestigationStore.getState().investigationMode === 'samurai'
        && useInvestigationStore.getState().status === 'running'
        && data.investigation_id
        && (data.evidence_extraction?.samurai_social_intel || data.tool_results?.length)
      ) {
        const painted = useInvestigationStore.getState().result;
        if (painted) s.setComplete(data.investigation_id, painted);
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
      if (!result) {
        wsFinished = true;
        ws.close();
        return;
      }
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
    if (epoch !== investigationEpoch) return;
    if (!wsFinished && useInvestigationStore.getState().status === 'running') {
      // Do not surface a hard error — onclose recovery will poll for results.
    }
  };

  ws.onclose = () => {
    if (activeWs !== ws) return;
    activeWs = null;
    if (epoch !== investigationEpoch) return;
    if (wsFinished || userStoppedInvestigation) return;
    const s = useInvestigationStore.getState();
    if (s.status !== 'running') return;

    const investigationId = s.investigationId;
    if (investigationId) {
      const qt = s.queryType;
      // Silent recovery only — never force the tool card back to a fake RUNNING state.
      void tryRecoverInvestigation(investigationId, epoch, {
        isImage: qt === 'image',
        isPhone: qt === 'phone' || qt === 'infra',
        mode: s.investigationMode,
      }).then((recovered) => {
        if (epoch !== investigationEpoch) return;
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
