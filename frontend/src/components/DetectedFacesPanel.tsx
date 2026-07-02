import type { DetectedFace, InvestigationResult } from '../types';
import { apiAssetUrl } from '../api/client';
import { Badge } from './ui/Badge';
import { ConfidenceBar } from './ui/ConfidenceBar';

function FaceCard({ face }: { face: DetectedFace }) {
  const preview = apiAssetUrl(face.crop_preview_url);
  const label = `Person ${face.person_index + 1}`;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-700/80 bg-slate-900/60">
      <div className="aspect-square bg-slate-950">
        {preview ? (
          <img
            src={preview}
            alt={label}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl text-slate-600">👤</div>
        )}
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-white">{label}</p>
          <span className="font-mono text-xs text-emerald-400">{(face.confidence * 100).toFixed(0)}%</span>
        </div>
        <Badge variant="muted">{face.source_tool}</Badge>
        {face.quality_score != null && face.quality_score > 0 && (
          <p className="text-[11px] text-slate-500">Face quality: {(face.quality_score * 100).toFixed(0)}%</p>
        )}
        <ConfidenceBar score={face.confidence * 100} />
        <p className="text-[10px] leading-relaxed text-slate-500">
          Isolated face crop from your upload — use this to verify which individual the system detected.
        </p>
      </div>
    </div>
  );
}

export function DetectedFacesPanel({ result }: { result: InvestigationResult }) {
  const correlation = result.image_correlation;
  const faces = correlation?.detected_faces ?? [];
  const seedPreview = apiAssetUrl(correlation?.seed_preview_url ?? null);
  const faceCount = faces.length;

  if (!faceCount && !seedPreview) return null;

  return (
    <section className="intel-card overflow-hidden">
      <div className="border-b border-slate-800/80 bg-slate-900/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">👥</span>
          <div>
            <h3 className="text-sm font-semibold text-white">Detected Faces</h3>
            <p className="text-[11px] text-slate-500">
              {faceCount
                ? `${faceCount} person${faceCount === 1 ? '' : 's'} isolated from your uploaded photo`
                : 'Uploaded photo — face crops unavailable for this run'}
            </p>
          </div>
          {faceCount > 0 && <Badge variant="info" className="ml-auto">{faceCount}</Badge>}
        </div>
      </div>
      <div className="grid gap-4 p-5 lg:grid-cols-[minmax(200px,280px)_1fr]">
        {seedPreview && (
          <div className="overflow-hidden rounded-xl border border-slate-700/80 bg-slate-950">
            <p className="border-b border-slate-800 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Original upload
            </p>
            <img
              src={seedPreview}
              alt="Uploaded investigation image"
              className="max-h-72 w-full object-contain"
              loading="lazy"
            />
          </div>
        )}
        {faceCount > 0 ? (
          <div className={`grid gap-3 ${faceCount === 1 ? 'grid-cols-1 max-w-xs' : 'grid-cols-2 sm:grid-cols-2'}`}>
            {faces.map((face) => (
              <FaceCard key={face.face_id} face={face} />
            ))}
          </div>
        ) : (
          <div className="flex items-center rounded-xl border border-dashed border-slate-700 px-4 py-6 text-sm text-slate-400">
            Face count was reported but crop images were not saved. Re-run the investigation after restarting the backend.
          </div>
        )}
      </div>
    </section>
  );
}
