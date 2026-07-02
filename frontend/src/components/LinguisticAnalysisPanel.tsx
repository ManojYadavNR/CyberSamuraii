import { useMemo } from 'react';
import { useInvestigationStore } from '../store/investigationStore';
import {
  engineBadge,
  entityKindIcon,
  languageLabel,
  linguisticFromResult,
  sentimentColor,
  type LinguisticNamedEntity,
} from '../lib/linguisticView';
import { CollapsibleSection } from './CollapsibleSection';
import { Badge } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 px-4 py-3">
      <p className="text-[10px] font-bold uppercase tracking-wider text-violet-300/80">{label}</p>
      <p className="mt-1 text-xl font-semibold text-white">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p>}
    </div>
  );
}

function LanguageBars({ distribution }: { distribution?: Record<string, number> }) {
  const entries = Object.entries(distribution ?? {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return (
    <div className="space-y-2">
      {entries.map(([lang, pct]) => (
        <div key={lang}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-slate-300">{languageLabel(lang)}</span>
            <span className="font-mono text-violet-300">{(pct * 100).toFixed(0)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-violet-600 to-fuchsia-500"
              style={{ width: `${Math.max(4, pct * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function EntityGroup({ kind, items }: { kind: string; items: LinguisticNamedEntity[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {entityKindIcon(kind)} {kind}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((ent, i) => (
          <span
            key={`${ent.text}-${i}`}
            className="rounded-md border border-slate-700/80 bg-slate-800/60 px-2 py-1 text-xs text-slate-200"
            title={ent.source_ref}
          >
            {ent.text}
            {ent.confidence != null && (
              <span className="ml-1 font-mono text-[10px] text-slate-500">
                {(ent.confidence * 100).toFixed(0)}%
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

export function LinguisticAnalysisPanel() {
  const result = useInvestigationStore((s) => s.result);
  const ling = useMemo(() => linguisticFromResult(result), [result]);

  const entitiesByKind = useMemo(() => {
    const map = new Map<string, LinguisticNamedEntity[]>();
    for (const ent of ling?.named_entities ?? []) {
      const kind = ent.kind || 'misc';
      if (!map.has(kind)) map.set(kind, []);
      map.get(kind)!.push(ent);
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [ling]);

  if (!result) return null;

  if (!ling) {
    return (
      <CollapsibleSection
        title="Linguistic Analysis"
        subtitle="ML language, sentiment, NER, topics, and authorship signals"
        badge="NLP"
        defaultOpen={false}
      >
        <EmptyState
          icon="📝"
          title="No text corpus yet"
          description="Run a username or profile investigation. Bios, posts, and search snippets are analyzed after evidence extraction."
        />
      </CollapsibleSection>
    );
  }

  const badge = engineBadge(ling.engine_mode);
  const sent = ling.sentiment_overview ?? {};
  const pos = Number(sent.positive_artifacts ?? 0);
  const neg = Number(sent.negative_artifacts ?? 0);
  const neu = Number(sent.neutral_artifacts ?? 0);
  const sentTotal = Math.max(1, pos + neg + neu);

  return (
    <section className="intel-card overflow-hidden border-violet-500/20">
      <header className="border-b border-violet-500/15 bg-gradient-to-r from-violet-950/40 to-fuchsia-950/20 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-[0.14em] text-violet-200">
              Linguistic Analysis
            </h3>
            <p className="mt-1 text-xs text-slate-400">
              Multilingual NLP — language ID, sentiment, NER, zero-shot topics, embeddings, toxicity
            </p>
          </div>
          <Badge variant={badge.variant === 'success' ? 'success' : 'warn'}>{badge.label}</Badge>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Artifacts" value={String(ling.artifacts_analyzed ?? 0)} sub="text sources" />
          <StatCard
            label="Characters"
            value={(ling.total_characters ?? 0).toLocaleString()}
            sub="corpus size"
          />
          <StatCard
            label="Primary language"
            value={languageLabel(ling.language_profile?.primary)}
            sub={`${ling.named_entities?.length ?? 0} entities`}
          />
          <StatCard
            label="Sentiment mix"
            value={`${Math.round((Number(sent.positive_ratio ?? 0)) * 100)}% +`}
            sub={`${neg} negative / ${neu} neutral`}
          />
        </div>
      </header>

      <div className="space-y-4 p-5">
        <CollapsibleSection
          title="Language profile"
          subtitle="XLM-RoBERTa language detection + script counts"
          badge={languageLabel(ling.language_profile?.primary)}
          defaultOpen
        >
          <LanguageBars distribution={ling.language_profile?.distribution} />
          {ling.language_profile?.scripts && (
            <p className="mt-3 text-xs text-slate-500">
              Scripts — Latin: {ling.language_profile.scripts.latin ?? 0} chars · Devanagari:{' '}
              {ling.language_profile.scripts.devanagari ?? 0} chars
            </p>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Topics"
          subtitle="Zero-shot multilingual topic classification"
          badge={String(ling.topics?.length ?? 0)}
          defaultOpen
        >
          <div className="space-y-2">
            {(ling.topics ?? []).map((t) => (
              <div
                key={t.topic}
                className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium capitalize text-slate-200">
                    {t.topic.replace(/_/g, ' ')}
                  </span>
                  <span className="font-mono text-xs text-violet-300">{(t.score * 100).toFixed(0)}%</span>
                </div>
                {t.evidence_snippets?.[0] && (
                  <p className="mt-2 text-xs leading-relaxed text-slate-500 line-clamp-2">
                    {t.evidence_snippets[0]}
                  </p>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Sentiment"
          subtitle="XLM-RoBERTa per-artifact sentiment"
          badge={`${pos + neg + neu}`}
          defaultOpen
        >
          <div className="mb-4 flex h-3 overflow-hidden rounded-full bg-slate-800">
            <div className="bg-emerald-500" style={{ width: `${(pos / sentTotal) * 100}%` }} />
            <div className="bg-slate-600" style={{ width: `${(neu / sentTotal) * 100}%` }} />
            <div className="bg-rose-500" style={{ width: `${(neg / sentTotal) * 100}%` }} />
          </div>
          <div className="space-y-2">
            {(ling.artifact_insights ?? []).slice(0, 12).map((ins, i) => (
              <div
                key={`${ins.source_ref}-${i}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-800/80 px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <span className="font-mono text-slate-400">{ins.source_tool}</span>
                  {ins.source_platform && (
                    <span className="ml-2 text-slate-500">· {ins.source_platform}</span>
                  )}
                  <span className="ml-2 text-slate-600">· {languageLabel(ins.language)}</span>
                </div>
                {ins.sentiment && (
                  <span className={sentimentColor(ins.sentiment.label)}>
                    {ins.sentiment.label}
                    {ins.sentiment.confidence != null && (
                      <span className="ml-1 font-mono text-slate-500">
                        {(ins.sentiment.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </span>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>

        {(ling.identity_signals?.length ?? 0) > 0 && (
          <CollapsibleSection
            title="Identity matches"
            subtitle="Seed username alignment in corpus and NER"
            badge={String(ling.identity_signals?.length)}
            defaultOpen
          >
            <div className="space-y-2">
              {(ling.identity_signals ?? []).map((sig, i) => (
                <div key={i} className="rounded-lg border border-emerald-500/25 bg-emerald-500/5 px-3 py-2 text-xs">
                  <div className="flex justify-between gap-2">
                    <span className="font-medium text-emerald-200">{sig.text}</span>
                    {sig.score != null && (
                      <span className="font-mono text-emerald-400">{(sig.score * 100).toFixed(0)}%</span>
                    )}
                  </div>
                  <p className="mt-1 text-slate-500">
                    {sig.kind?.replace(/_/g, ' ')} · {sig.source}
                  </p>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        <CollapsibleSection
          title="Named entities"
          subtitle="WikiNEuRal multilingual NER + regex intel"
          badge={String(ling.named_entities?.length ?? 0)}
          defaultOpen={false}
        >
          <div className="space-y-3">
            {entitiesByKind.map(([kind, items]) => (
              <EntityGroup key={kind} kind={kind} items={items.slice(0, 24)} />
            ))}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Keywords"
          subtitle="KeyBERT embedding keywords"
          badge={String(ling.keywords?.length ?? 0)}
          defaultOpen={false}
        >
          <div className="flex flex-wrap gap-2">
            {(ling.keywords ?? []).map((kw) => (
              <Badge key={kw} variant="muted">{kw}</Badge>
            ))}
          </div>
        </CollapsibleSection>

        {(ling.cross_links?.length ?? 0) > 0 && (
          <CollapsibleSection
            title="Cross-text links"
            subtitle="Semantic embeddings + stylometry"
            badge={String(ling.cross_links?.length)}
            defaultOpen={false}
          >
            <div className="space-y-2">
              {(ling.cross_links ?? []).map((link, i) => (
                <div key={i} className="rounded-lg border border-slate-800 px-3 py-2 text-xs">
                  <div className="flex justify-between gap-2">
                    <span className="font-medium text-violet-300">{link.kind}</span>
                    {link.score != null && (
                      <span className="font-mono text-slate-500">{(link.score * 100).toFixed(0)}%</span>
                    )}
                  </div>
                  <p className="mt-1 text-slate-400">{link.detail}</p>
                  <p className="mt-1 font-mono text-[10px] text-slate-600">
                    {(link.sources ?? []).join(' ↔ ')}
                  </p>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {(ling.contradictions?.length ?? 0) > 0 && (
          <CollapsibleSection
            title="Contradictions"
            subtitle="Conflicting locations, names, or organizations"
            badge={String(ling.contradictions?.length)}
            defaultOpen={false}
          >
            <div className="space-y-2">
              {(ling.contradictions ?? []).map((c, i) => (
                <div key={i} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
                  <span className="font-semibold uppercase text-amber-400">{c.type}</span>
                  <p className="mt-1 text-slate-300">{c.detail}</p>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {(ling.threat_flags?.length ?? 0) > 0 && (
          <CollapsibleSection
            title="Threat & toxicity flags"
            subtitle="Lexicon + Toxic-BERT — human review required"
            badge={String(ling.threat_flags?.length)}
            defaultOpen={false}
          >
            <div className="space-y-2">
              {(ling.threat_flags ?? []).map((f, i) => (
                <div key={i} className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs">
                  <p className="text-rose-200">{String(f.phrase ?? '')}</p>
                  <p className="mt-1 text-slate-500">
                    {String(f.source_ref ?? '')} · conf {String(f.confidence ?? '')}
                  </p>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        <CollapsibleSection
          title="Corpus sample"
          subtitle="Raw text artifacts analyzed"
          badge={String(ling.corpus_sample?.length ?? 0)}
          defaultOpen={false}
        >
          <div className="space-y-3">
            {(ling.corpus_sample ?? []).map((art, i) => (
              <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <div className="mb-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wider text-slate-500">
                  <span>{art.source_tool}</span>
                  {art.source_platform && <span>· {art.source_platform}</span>}
                  <span>· {languageLabel(art.detected_language)}</span>
                </div>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{art.text}</p>
              </div>
            ))}
          </div>
        </CollapsibleSection>

        {ling.models_used && Object.keys(ling.models_used).length > 0 && (
          <CollapsibleSection title="ML models" subtitle="Pipelines used for this analysis" defaultOpen={false}>
            <div className="space-y-1 font-mono text-[10px] text-slate-500">
              {Object.entries(ling.models_used).map(([k, v]) => (
                <p key={k}>
                  <span className="text-violet-400">{k}</span>: {v}
                </p>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>
    </section>
  );
}
