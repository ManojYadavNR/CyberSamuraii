import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export interface IntelSelectOption<T extends string = string> {
  value: T;
  label: string;
  hint?: string;
  icon?: ReactNode;
  disabled?: boolean;
}

interface IntelSelectProps<T extends string = string> {
  id?: string;
  label?: string;
  value: T;
  options: IntelSelectOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  size?: 'sm' | 'md';
  align?: 'left' | 'right';
  maxMenuHeight?: number;
}

export function IntelSelect<T extends string = string>({
  id,
  label,
  value,
  options,
  onChange,
  disabled = false,
  placeholder = 'Select…',
  className = '',
  size = 'md',
  align = 'left',
  maxMenuHeight = 280,
}: IntelSelectProps<T>) {
  const autoId = useId();
  const selectId = id || autoId;
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<{ top: number; left: number; width: number } | null>(null);

  const selected = options.find((o) => o.value === value);

  const updateMenuPosition = () => {
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const width = Math.max(rect.width, 220);
    const left = align === 'right' ? rect.right - width : rect.left;
    setMenuStyle({
      top: rect.bottom + 6,
      left,
      width,
    });
  };

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const onScroll = () => updateMenuPosition();
    const onResize = () => updateMenuPosition();
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, align]);

  const pick = (next: T) => {
    onChange(next);
    setOpen(false);
  };

  const sizeClass = size === 'sm' ? 'intel-select-trigger--sm' : '';

  return (
    <div ref={rootRef} className={`intel-select-root ${className}`}>
      {label && (
        <label htmlFor={selectId} className="intel-select-label">
          {label}
        </label>
      )}
      <button
        id={selectId}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (disabled) return;
          setOpen((v) => !v);
        }}
        className={`intel-select-trigger ${sizeClass} ${open ? 'intel-select-trigger--open' : ''} ${disabled ? 'intel-select-trigger--disabled' : ''}`}
      >
        <span className="intel-select-trigger__content">
          {selected?.icon && <span className="intel-select-trigger__icon">{selected.icon}</span>}
          <span className="intel-select-trigger__text">
            <span className="intel-select-trigger__label">{selected?.label || placeholder}</span>
            {selected?.hint && size === 'md' && (
              <span className="intel-select-trigger__hint">{selected.hint}</span>
            )}
          </span>
        </span>
        <span className={`intel-select-chevron ${open ? 'intel-select-chevron--open' : ''}`} aria-hidden>
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
            <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open && menuStyle && createPortal(
        <div
          ref={menuRef}
          className="intel-select-menu intel-select-menu--enter"
          style={{
            top: menuStyle.top,
            left: menuStyle.left,
            width: menuStyle.width,
            maxHeight: maxMenuHeight,
          }}
          role="listbox"
          aria-labelledby={selectId}
        >
          <ul className="intel-select-menu__list">
            {options.map((opt) => {
              const active = opt.value === value;
              return (
                <li key={opt.value}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    disabled={opt.disabled}
                    onClick={() => !opt.disabled && pick(opt.value)}
                    className={`intel-select-option ${active ? 'intel-select-option--active' : ''} ${opt.disabled ? 'intel-select-option--disabled' : ''}`}
                  >
                    {opt.icon && <span className="intel-select-option__icon">{opt.icon}</span>}
                    <span className="intel-select-option__body">
                      <span className="intel-select-option__label">{opt.label}</span>
                      {opt.hint && <span className="intel-select-option__hint">{opt.hint}</span>}
                    </span>
                    {active && (
                      <span className="intel-select-option__check" aria-hidden>
                        <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                          <path d="M5 10l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>,
        document.body,
      )}
    </div>
  );
}
