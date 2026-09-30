import React from 'react';
import { Card } from './ui.jsx';

const sec = (ms) => `${(ms / 1000).toFixed(1)} sec`;

/** Builds displayed numbers from REAL backend timings and browser-measured round trips. */
export function summarizeTiming(t) {
  const archVal =
    (t.validations || []).reduce(
      (n, x) => n + (x.architecture_validation_ms || 0),
      0
    ) +
    ((t.analyze && t.analyze.server.architecture_validation_ms) || 0);

  const stages = [
    [
      'Image Analysis',
      (t.analyze &&
        (t.analyze.server.image_analysis_ms || 0) +
        (t.analyze.server.image_decode_ms || 0)) ||
        0,
      t.analyze && t.analyze.server.cache_hit,
    ],
    ['Architecture Validation', archVal],
    [
      'Code Generation',
      t.generate
        ? (t.generate.server.code_generation_ms || 0) +
          (t.generate.server.requirements_ms || 0)
        : 0,
    ],
    [
      'Final Validation',
      t.verify ? t.verify.server.final_validation_ms || 0 : 0,
    ],
  ];

  const backend = stages.reduce((n, s) => n + s[1], 0);

  const roundTrips =
    ((t.analyze && t.analyze.roundTripMs) || 0) +
    ((t.generate && t.generate.roundTripMs) || 0) +
    ((t.verify && t.verify.roundTripMs) || 0);

  const slowest = stages.reduce((a, b) => (b[1] > a[1] ? b : a));

  return { stages, backend, roundTrips, slowest };
}

function StageRow({ name, ms, source }) {
  const percentage = Math.min(
    100,
    Math.max(3, (ms / Math.max(1, source)) * 100)
  );

  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-700">{name}</span>
        <span className="mono text-sm font-bold text-slate-900">
          {sec(ms)}
        </span>
      </div>

      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-indigo-500 transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export default function Timings({ timing, source }) {
  const s = summarizeTiming(timing);
  const within = s.roundTrips <= 10000;

  return (
    <Card
      title="⚡ Performance & Pipeline Timing"
      subtitle="Measured from the real backend and browser. Review time is not included."
    >
      {/* Main performance summary */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
            Total browser time
          </p>

          <p className="mt-1 text-4xl font-extrabold tracking-tight text-indigo-950">
            {sec(s.roundTrips)}
          </p>

          <p className="mt-1 text-xs text-indigo-700">
            Upload → generated & verified output
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Backend processing
          </p>

          <p className="mt-1 text-4xl font-extrabold tracking-tight text-slate-900">
            {sec(s.backend)}
          </p>

          <p className="mt-1 text-xs text-slate-500">
            Server-side measured processing
          </p>
        </div>

        <div
          className={`rounded-2xl border p-5 ${
            within
              ? 'border-emerald-200 bg-emerald-50'
              : 'border-amber-200 bg-amber-50'
          }`}
        >
          <p
            className={`text-xs font-semibold uppercase tracking-wider ${
              within ? 'text-emerald-700' : 'text-amber-700'
            }`}
          >
            Performance target
          </p>

          <p
            className={`mt-1 text-2xl font-extrabold ${
              within ? 'text-emerald-900' : 'text-amber-900'
            }`}
          >
            {within ? '✓ Within target' : '⚠ Above target'}
          </p>

          <p
            className={`mt-1 text-xs ${
              within ? 'text-emerald-700' : 'text-amber-700'
            }`}
          >
            Target: ≤ 10 seconds
          </p>
        </div>
      </div>

      {/* Pipeline stages */}
      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Pipeline breakdown
            </h3>
            <p className="text-xs text-slate-500">
              Time measured for each processing stage
            </p>
          </div>

          {source === 'cache' && (
            <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-800">
              ⚡ Cached analysis
            </span>
          )}

          {source === 'fixture' && (
            <span className="rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-800">
              Offline fixture
            </span>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {s.stages.map(([name, ms]) => (
            <StageRow
              key={name}
              name={name}
              ms={ms}
              source={Math.max(s.backend, 1)}
            />
          ))}
        </div>
      </div>

      {/* Slowest stage */}
      <div className="mt-5 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Slowest stage
            </p>
            <p className="mt-1 font-semibold text-slate-900">
              {s.slowest[0]}
            </p>
          </div>

          <span className="mono rounded-lg bg-slate-100 px-3 py-2 text-sm font-bold text-slate-800">
            {sec(s.slowest[1])}
          </span>
        </div>

        {s.slowest[0] === 'Image Analysis' && (
          <p className="mt-2 text-xs text-slate-500">
            Image analysis is typically the most expensive stage because it
            processes the architecture diagram.
          </p>
        )}
      </div>

      {/* Detailed measurements */}
      <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700">
          View detailed timing measurements
        </summary>

        <div className="border-t border-slate-200 bg-white p-4">
          <table className="w-full text-sm" data-testid="timings">
            <tbody>
              {s.stages.map(([name, ms]) => (
                <tr key={name} className="border-b border-slate-100">
                  <td className="py-2">{name}</td>
                  <td className="mono py-2 text-right">{sec(ms)}</td>
                </tr>
              ))}

              <tr className="font-semibold">
                <td className="py-2">Total backend processing</td>
                <td className="mono py-2 text-right">{sec(s.backend)}</td>
              </tr>

              <tr className="text-slate-600">
                <td className="py-2">
                  Upload → final code, browser round trip
                </td>
                <td className="mono py-2 text-right">{sec(s.roundTrips)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      {/* Target status */}
      <div
        className={`mt-4 rounded-xl px-4 py-3 ${
          within
            ? 'bg-emerald-50 text-emerald-900'
            : 'bg-amber-50 text-amber-900'
        }`}
      >
        <p className="text-sm font-semibold">
          {within
            ? `✓ Within the 10 second target (${sec(s.roundTrips)}).`
            : `⚠ Above the 10 second target (${sec(
                s.roundTrips
              )}). Slowest stage: ${s.slowest[0]} (${sec(s.slowest[1])}).`}
        </p>

        <p className="mt-1 text-xs opacity-80">
          This value is measured from the actual browser round trip; it is not
          a simulated performance number.
        </p>
      </div>
    </Card>
  );
}