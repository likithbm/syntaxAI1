import React, { useEffect, useRef, useState } from 'react';
import { Card } from './ui.jsx';

/**
 * Processing panel: never a blank screen. `messages` are shown in order; when `activeIndex` is provided
 * (generate / verify are separate requests) it reflects the real stage, otherwise the message advances over time.
 * The elapsed timer is real wall-clock time.
 */
export default function Progress({ title, messages, activeIndex = null, note }) {
  const [elapsed, setElapsed] = useState(0);
  const t0 = useRef(performance.now());
  useEffect(() => {
    t0.current = performance.now();
    const id = setInterval(() => setElapsed(performance.now() - t0.current), 100);
    return () => clearInterval(id);
  }, [title]);
  const auto = Math.min(messages.length - 1, Math.floor(elapsed / 1600));
  const active = activeIndex == null ? auto : activeIndex;
  return (
    <Card title={title} right={<span className="mono text-sm text-slate-500" aria-label="elapsed time">{(elapsed / 1000).toFixed(1)} s</span>}>
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-busy="true">
        <div className="indeterminate h-2 rounded-full bg-indigo-500" />
      </div>
      <ul className="space-y-2" aria-live="polite">
        {messages.map((m, i) => (
          <li key={m} className={`flex items-center gap-2 text-sm ${i === active ? 'font-medium text-slate-900' : i < active ? 'text-slate-500' : 'text-slate-300'}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${i < active ? 'bg-emerald-100 text-emerald-700' : i === active ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100'}`}>
              {i < active ? '✓' : i === active ? '…' : ''}
            </span>
            {m}
          </li>
        ))}
      </ul>
      {note && <p className="mt-4 text-xs text-slate-500">{note}</p>}
    </Card>
  );
}
