type SpinnerProps = {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'ring' | 'dots';
  className?: string;
  label?: string;
};

const SIZES = {
  sm: 'spinner--sm',
  md: 'spinner--md',
  lg: 'spinner--lg',
} as const;

export function Spinner({ size = 'md', variant = 'ring', className = '', label }: SpinnerProps) {
  if (variant === 'dots') {
    return (
      <span className={`spinner-dots ${className}`} role="status" aria-label={label || 'Loading'}>
        <span className="spinner-dots__dot" />
        <span className="spinner-dots__dot" />
        <span className="spinner-dots__dot" />
      </span>
    );
  }

  return (
    <span className={`spinner-ring ${SIZES[size]} ${className}`} role="status" aria-label={label || 'Loading'}>
      <span className="spinner-ring__track" />
      <span className="spinner-ring__arc" />
    </span>
  );
}
