import React from 'react';

export const SEVERITY = {
  critical: { icon: '🔴', label: 'Critical', box: 'border-red-300 bg-red-50', badge: 'bg-red-100 text-red-800 ring-red-200', bar: 'bg-red-500' },
  warning: { icon: '🟠', label: 'Warning', box: 'border-orange-300 bg-orange-50', badge: 'bg-orange-100 text-orange-800 ring-orange-200', bar: 'bg-orange-500' },
  recommendation: { icon: '🟡', label: 'Recommendation', box: 'border-yellow-300 bg-yellow-50', badge: 'bg-yellow-100 text-yellow-800 ring-yellow-200', bar: 'bg-yellow-400' },
  valid: { icon: '🟢', label: 'Valid', box: 'border-green-300 bg-green-50', badge: 'bg-green-100 text-green-800 ring-green-200', bar: 'bg-green-500' },
};

export function SeverityBadge({ severity }) {
  const s = SEVERITY[severity] || SEVERITY.warning;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${s.badge}`}>
      <span aria-hidden="true">{s.icon}</span> {s.label}
    </span>
  );
}

export function SourceTag({ source }) {
  const ai = source === 'ai';
  return (
    <span
      title={ai ? 'Reported by the AI model from the image. Advisory only - it never blocks generation.' : 'Produced by a fixed, deterministic rule.'}
      className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${ai ? 'bg-violet-100 text-violet-800' : 'bg-slate-200 text-slate-700'}`}
    >
      {ai ? 'AI recommendation' : 'Deterministic rule'}
    </span>
  );
}

const BTN = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300',
  secondary: 'bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
  ghost: 'text-slate-600 hover:bg-slate-100 disabled:text-slate-300',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-300',
};

export function Button({ variant = 'secondary', size = 'md', className = '', ...props }) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-4 py-2 text-sm';
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed ${pad} ${BTN[variant]} ${className}`}
    />
  );
}

export function Card({ title, subtitle, right, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function ErrorBanner({ error, onRetry, onDismiss }) {
  if (!error) return null;
  return (
    <div role="alert" className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{error.title || 'Something went wrong'}</p>
          <p className="mt-1">{error.message}</p>
          {error.code && <p className="mono mt-1 text-xs text-red-700">code: {error.code}</p>}
          {error.detailsList && error.detailsList.length > 0 && (
            <ul className="mt-2 list-disc pl-5">{error.detailsList.map((d) => <li key={d}>{d}</li>)}</ul>
          )}
          <p className="mt-2 text-xs text-red-700">Your uploaded image and your refinements have been kept.</p>
        </div>
        <div className="flex shrink-0 gap-2">
          {onRetry && error.retryable !== false && <Button variant="danger" size="sm" onClick={onRetry}>Retry</Button>}
          {onDismiss && <Button variant="secondary" size="sm" onClick={onDismiss}>Dismiss</Button>}
        </div>
      </div>
    </div>
  );
}

export function Check({ status }) {
  const map = { pass: ['✓', 'text-emerald-700 bg-emerald-100'], warn: ['!', 'text-amber-800 bg-amber-100'], fail: ['✕', 'text-red-700 bg-red-100'], 'n/a': ['–', 'text-slate-500 bg-slate-100'] };
  const [sym, cls] = map[status] || map['n/a'];
  return <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${cls}`} aria-label={status}>{sym}</span>;
}
