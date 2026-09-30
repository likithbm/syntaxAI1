import React from 'react';

export const STEPS = ['Upload', 'Analyze', 'Review', 'Refine', 'Validate', 'Generate', 'Verify', 'Download'];

export function stepIndex(phase, genStage) {
  switch (phase) {
    case 'upload': return 0;
    case 'analyzing': return 1;
    case 'review': return 2;
    case 'refine': return 3;
    case 'validate': return 4;
    case 'requirements': return 5;
    case 'generating': return genStage === 'verify' ? 6 : 5;
    case 'result': return 7;
    default: return 0;
  }
}

export default function Stepper({ phase, genStage, onGoto, reached }) {
  const current = stepIndex(phase, genStage);
  const busy = phase === 'analyzing' || phase === 'generating';
  return (
    <nav aria-label="Progress" className="mb-6">
      <ol className="flex flex-wrap items-center gap-y-2">
        {STEPS.map((label, i) => {
          const done = i < current || phase === 'result' && i === 7;
          const active = i === current;
          const clickable = !busy && onGoto && reached && reached[i] && i !== current && i < current;
          return (
            <li key={label} className="flex items-center">
              <button
                type="button"
                disabled={!clickable}
                onClick={() => clickable && onGoto(i)}
                aria-current={active ? 'step' : undefined}
                className={`flex items-center gap-2 rounded-full px-2 py-1 text-sm ${clickable ? 'cursor-pointer hover:bg-slate-100' : 'cursor-default'}`}
              >
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                    active ? 'bg-indigo-600 text-white ring-4 ring-indigo-100' : done ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </span>
                <span className={active ? 'font-semibold text-slate-900' : done ? 'text-slate-700' : 'text-slate-400'}>{label}</span>
                {active && busy && <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" aria-label="working" />}
              </button>
              {i < STEPS.length - 1 && <span className={`mx-1 h-px w-4 sm:w-6 ${i < current ? 'bg-emerald-400' : 'bg-slate-200'}`} />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
