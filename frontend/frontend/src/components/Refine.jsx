import React from 'react';
import { Button, Card } from './ui.jsx';

export const OPTIONS = [
  ['encryption', 'Enable encryption'],
  ['private_subnets', 'Use private subnets'],
  ['iam_least_privilege', 'Apply IAM least privilege'],
  ['cloudwatch_logging', 'Enable CloudWatch logging'],
  ['security_groups', 'Add security groups'],
  ['multi_az', 'Multi-AZ deployment'],
  ['backups', 'Enable backups'],
  ['https_tls', 'Add HTTPS/TLS'],
  ['monitoring', 'Add monitoring'],
  ['cost_optimization', 'Cost optimization'],
];

export function OptionChecks({ selected, onToggle, active = [] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {OPTIONS.map(([id, label]) => {
        const isActive = active.includes(id);
        return (
          <label key={id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${selected.includes(id) ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'}`}>
            <input type="checkbox" checked={selected.includes(id)} onChange={() => onToggle(id)} />
            <span>{label}</span>
            {isActive && <span className="ml-auto rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] text-emerald-800">already applied</span>}
          </label>
        );
      })}
    </div>
  );
}

export default function Refine({ arch, options, text, onOptions, onText, onApply, onSkip, onOps, busy, last }) {
  const toggle = (id) => onOptions(options.includes(id) ? options.filter((o) => o !== id) : [...options, id]);
  const active = OPTIONS.map(([id]) => id).filter((id) => arch.requirements[id]);
  const notes = arch.requirements.notes || [];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card title="Would you like to refine or modify the detected architecture before generating the code?"
          subtitle="Your requirements are applied to the architecture, then it is validated again. Nothing is generated yet.">
          <label htmlFor="refine-text" className="mb-1 block text-sm font-semibold text-slate-800">Architecture Refinements</label>
          <textarea id="refine-text" value={text} onChange={(e) => onText(e.target.value)} rows={4}
            placeholder="Example: Make RDS private, enable encryption for S3 and RDS, use least-privilege IAM, add an Application Load Balancer, use 2 Availability Zones..."
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200" />
          <p className="mt-1 text-xs text-slate-500">Anything that cannot be mapped to an architecture change is reported back to you and recorded as a note, never silently dropped. This box is also where you enter “Other requirements”.</p>
          <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-800">Refinement options</h3>
          <OptionChecks selected={options} onToggle={toggle} active={active} />
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <Button onClick={onSkip} disabled={busy}>No changes - continue to validation</Button>
            <Button variant="primary" onClick={onApply} disabled={busy || (!text.trim() && options.length === 0)}>Apply & re-validate</Button>
          </div>
        </Card>
      </div>
      <div className="space-y-4">
        <Card title="Active requirements" subtitle="Edit, add or remove">
          {active.length === 0 && notes.length === 0 && <p className="text-sm text-slate-500">None yet.</p>}
          <ul className="space-y-1.5 text-sm">
            {active.map((id) => (
              <li key={id} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
                <span>{OPTIONS.find(([o]) => o === id)[1]}</span>
                <Button size="sm" variant="ghost" onClick={() => onOps([{ op: 'set_requirement', key: id, value: false }])}>Remove</Button>
              </li>
            ))}
            {notes.map((n, i) => (
              <li key={n + i} className="flex items-start justify-between gap-2 rounded bg-slate-50 px-2 py-1">
                <span className="text-slate-700">📝 {n}</span>
                <Button size="sm" variant="ghost" onClick={() => onOps([{ op: 'remove_note', index: i }])}>Remove</Button>
              </li>
            ))}
          </ul>
        </Card>
        {last && (
          <Card title="Last refinement result">
            <p className="text-xs text-slate-500">Interpreted by: {last.interpreter ? (last.interpreter === 'bedrock' ? 'AI (Bedrock)' : 'built-in rules') : 'checkbox options only'}</p>
            {last.applied.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">{last.applied.map((a) => <li key={a}>{a}</li>)}</ul>}
            {last.unmapped.length > 0 && (
              <div className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900">
                <p className="font-medium">Could not be applied automatically:</p>
                <ul className="list-disc pl-5">{last.unmapped.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            )}
            {last.rejected.length > 0 && <p className="mt-2 text-xs text-red-700">{last.rejected.length} suggested change(s) were rejected as invalid.</p>}
            {last.warnings.map((w) => <p key={w} className="mt-2 text-xs text-amber-800">{w}</p>)}
          </Card>
        )}
      </div>
    </div>
  );
}
