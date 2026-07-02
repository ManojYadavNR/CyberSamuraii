import type { LeadVisual } from '../types';
import { dedupeByUrl } from './dedupeUrl';
import { seedInDorkContext } from './googleDorkView';

export function leadVisualsFromResult(
  result: {
    evidence_extraction?: { lead_visuals?: LeadVisual[] };
  } | null,
  seedQuery = '',
): LeadVisual[] {
  const leads = result?.evidence_extraction?.lead_visuals ?? [];
  const filtered = !seedQuery.trim()
    ? leads
    : leads.filter((lead) => {
      if (lead.lead_type === 'profile') return true;
      return seedInDorkContext(
        { url: lead.url, title: lead.title, snippet: lead.snippet },
        seedQuery,
      );
    });
  return dedupeByUrl(filtered, (lead) => lead.url);
}

export function leadTypeLabel(type: string): string {
  const map: Record<string, string> = {
    hackathon: 'Hackathon',
    event: 'Event',
    news: 'News',
    college: 'College',
    article: 'Article',
    video: 'Video',
    profile: 'Profile',
    achievement: 'Achievement',
    mention: 'Mention',
  };
  return map[type] || type;
}

export { resolveMediaUrl } from './mediaUrl';
