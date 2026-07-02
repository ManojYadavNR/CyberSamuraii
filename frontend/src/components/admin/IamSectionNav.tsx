import type { IamSection } from './iamTypes';

const SECTIONS: { id: IamSection; label: string }[] = [
  { id: 'identity', label: 'Identity & Access' },
  { id: 'organization', label: 'Organization' },
  { id: 'security', label: 'Security' },
  { id: 'system', label: 'System' },
];

export function IamSectionNav({ active, onSelect }: { active: IamSection; onSelect: (s: IamSection) => void }) {
  const scrollTo = (id: IamSection) => {
    onSelect(id);
    document.getElementById(`iam-section-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <nav className="iam-section-nav" aria-label="Administration sections">
      {SECTIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          className={`iam-section-pill ${active === s.id ? 'iam-section-pill--active' : ''}`}
          onClick={() => scrollTo(s.id)}
        >
          {s.label}
        </button>
      ))}
    </nav>
  );
}
