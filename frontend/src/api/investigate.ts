import { getWsUrl, fetchReviews, fetchInvestigation } from './client';
import type { InvestigationResult } from '../types';
import { useInvestigationStore } from '../store/investigationStore';

async function loadReviewsForInvestigation(id: string) {
  try {
    const data = await fetchReviews(id);
    useInvestigationStore.getState().setReviews(data.reviews);
  } catch {
    /* reviews optional */
  }
}

export function startInvestigation(query: string, queryType?: string, timeout = 180): void {
  const store = useInvestigationStore.getState();
  store.reset();
  store.setQuery(query);
  store.setRunning();

  const ws = new WebSocket(getWsUrl());

  ws.onopen = () => {
    ws.send(JSON.stringify({ query, query_type: queryType === 'auto' ? undefined : queryType, timeout_per_tool: timeout }));
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const s = useInvestigationStore.getState();

    if (data.error) {
      s.setError(data.error);
      ws.close();
      return;
    }

    if (data.query_type) {
      useInvestigationStore.setState({ queryType: data.query_type });
    }

    if (data.phase === 'tool') {
      s.updateToolProgress(data.tool, {
        status: data.status === 'running' ? 'running' : data.success ? 'done' : 'failed',
        success: data.success,
        execution_time_ms: data.execution_time_ms,
        error: data.error,
      });
    } else if (data.phase) {
      s.setPhase(data.phase);
    }

    if (data.phase === 'finished' || data.phase === 'complete') {
      const result = data.result as InvestigationResult;
      s.setComplete(data.investigation_id, result);
      useInvestigationStore.getState().addRecent({
        id: data.investigation_id,
        query: useInvestigationStore.getState().query,
        queryType: useInvestigationStore.getState().queryType,
        completedAt: new Date().toISOString(),
      });
      loadReviewsForInvestigation(data.investigation_id);
      ws.close();
    }
  };

  ws.onerror = () => {
    useInvestigationStore.getState().setError('WebSocket connection failed. Is the backend running on port 8000?');
  };

  ws.onclose = () => {
    const s = useInvestigationStore.getState();
    if (s.status === 'running') {
      s.setError('Investigation connection closed before completion. The server may have timed out — try again.');
    }
  };
}

export async function loadInvestigationById(id: string): Promise<void> {
  const inv = await fetchInvestigation(id);
  if (!inv.result) throw new Error('Investigation has no result data');
  useInvestigationStore.getState().loadFromServer(inv.id, inv.query, inv.query_type, inv.result);
  await loadReviewsForInvestigation(id);
}
