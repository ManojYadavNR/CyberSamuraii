import type { InvestigationResult } from '../types';
import { getVerifiedPlatformDetails } from './platformAccountView';

/** Verified platforms — merges identity profile + correlation (matches VerifiedPlatformsPanel). */
export function verifiedPlatformCount(result: InvestigationResult | null): number {
  return getVerifiedPlatformDetails(result).length;
}

/** Distinct intelligence sources (tools + verified platforms). */
export function totalSourceCount(result: InvestigationResult | null): number {
  if (!result) return 0;
  const sources = new Set<string>();
  for (const d of getVerifiedPlatformDetails(result)) {
    if (d.platform) sources.add(d.platform.toLowerCase());
    d.sources.forEach((s) => sources.add(s));
  }
  for (const tr of result.tool_results ?? []) {
    if (tr.success !== false) sources.add(tr.tool);
  }
  const count = sources.size;
  return count > 0 ? count : verifiedPlatformCount(result);
}
