import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

export function Modal({ open, onClose, title, children, wide = false }) {
  const ref = useRef(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onCloseRef.current();
    };
    ref.current?.focus();
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`card p-6 w-full animate-fade-in ${wide ? 'max-w-2xl' : 'max-w-md'}`}
        style={{ maxHeight: '90vh', overflowY: 'auto' }}>
        <div className="flex items-center justify-between mb-5">
          <h2 id={titleId} className="text-lg font-semibold themed-text-primary">{title}</h2>
          <button
            type="button"
            aria-label={`Close ${title}`}
            onClick={onClose}
            className="themed-text-muted hover:themed-text-primary transition-colors"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const SEV_COLORS = {
  critical: 'bg-red-600/15 text-red-500 border-red-600/30',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  low: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  info: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
};

export function SeverityBadge({ severity }) {
  return <span className={`badge border ${SEV_COLORS[severity] || SEV_COLORS.info}`}>{severity}</span>;
}

const STATUS_COLORS = {
  active: 'bg-green-500/15 text-green-400 border-green-500/30',
  completed: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  archived: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
};

export function StatusBadge({ status }) {
  return (
    <span className={`badge border ${STATUS_COLORS[status] || STATUS_COLORS.active}`}>
      {status === 'active' && <span className="w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 pulse-dot" />}
      {status}
    </span>
  );
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
        style={{ backgroundColor: 'var(--bg-700)' }}>
        <Icon size={24} className="themed-text-muted" />
      </div>
      <h3 className="text-base font-medium themed-text-secondary mb-1">{title}</h3>
      <p className="text-sm themed-text-muted max-w-sm mb-5">{description}</p>
      {action}
    </div>
  );
}

export function Spinner({ className = '', style = {} }) {
  return <div className={`w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin ${className}`} style={style} />;
}

export function Toast({ message, type = 'info', onDismiss }) {
  const colors = {
    error: 'border-red-500 bg-red-500/10 text-red-400',
    success: 'border-green-500 bg-green-500/10 text-green-400',
    info: 'border-blue-500 bg-blue-500/10 text-blue-400',
  };
  useEffect(() => { const t = setTimeout(onDismiss, 5000); return () => clearTimeout(t); }, [onDismiss]);
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg border font-mono text-sm animate-fade-in ${colors[type]}`}>
      {message}
    </div>
  );
}

export function SectionHeader({ title, description, action }) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h2 className="text-xl font-semibold themed-text-primary">{title}</h2>
        {description && <p className="text-sm themed-text-muted mt-1">{description}</p>}
      </div>
      {action}
    </div>
  );
}
