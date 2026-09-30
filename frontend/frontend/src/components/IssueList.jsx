import React, { useState } from 'react';
import { Button, SEVERITY, SeverityBadge, SourceTag } from './ui.jsx';
import { SUPPORTED, TYPE_LABELS } from './ArchitectureView.jsx';

/** Component editor: turns form changes into whitelisted patch operations (sent to the backend, which re-validates). */
export function EditDialog({ service, onApply, onClose }) {
  const p = service.properties;
  const [label, setLabel] = useState(service.label);
  const [type, setType] = useState(service.type);
  const [tier, setTier] = useState(service.tier);
  const [encrypted, setEncrypted] = useState(p.encrypted === null ? 'unset' : String(p.encrypted));
  const [multiAz, setMultiAz] = useState(p.multi_az === null ? 'unset' : String(p.multi_az));
  const [backup, setBackup] = useState(p.backup_retention == null ? '' : String(p.backup_retention));
  const [engine, setEngine] = useState(p.engine || '');
  const [isPublic, setIsPublic] = useState(p.public === null ? 'unset' : String(p.public));

  const submit = () => {
    const ops = [];
    const t = service.id;
    if (label.trim() && label !== service.label) ops.push({ op: 'rename', target: t, label: label.trim() });
    if (type !== service.type) ops.push({ op: 'set_type', target: t, type });
    if (tier !== service.tier && (tier === 'public' || tier === 'private')) ops.push({ op: 'set_tier', target: t, tier });
    const tri = (v) => (v === 'unset' ? null : v === 'true');
    if (['s3', 'rds', 'dynamodb', 'sqs', 'sns'].includes(type) && tri(encrypted) !== p.encrypted && encrypted !== 'unset') ops.push({ op: 'set_property', target: t, key: 'encrypted', value: tri(encrypted) });
    if (['s3', 'rds'].includes(type) && isPublic !== (p.public === null ? 'unset' : String(p.public)) && isPublic !== 'unset') ops.push({ op: 'set_property', target: t, key: 'public', value: tri(isPublic) });
    if (type === 'rds') {
      if (multiAz !== (p.multi_az === null ? 'unset' : String(p.multi_az)) && multiAz !== 'unset') ops.push({ op: 'set_property', target: t, key: 'multi_az', value: tri(multiAz) });
      if (backup !== '' && Number(backup) !== p.backup_retention) ops.push({ op: 'set_property', target: t, key: 'backup_retention', value: Number(backup) });
      if (engine && engine !== p.engine) ops.push({ op: 'set_property', target: t, key: 'engine', value: engine });
    }
    onApply(ops);
  };

  const tri = (value, set, name) => (
    <select aria-label={name} value={value} onChange={(e) => set(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
      <option value="unset">not specified</option>
      <option value="true">yes</option>
      <option value="false">no</option>
    </select>
  );
  const Field = ({ name, children }) => (
    <label className="block text-sm"><span className="mb-1 block font-medium text-slate-700">{name}</span>{children}</label>
  );

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-label={`Edit ${service.label}`}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
        <h3 className="text-lg font-semibold">Edit component</h3>
        <p className="mono mb-4 text-xs text-slate-400">{service.id}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field name="Name"><input value={label} onChange={(e) => setLabel(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" /></Field>
          <Field name="AWS service">
            <select value={type} onChange={(e) => setType(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
              {SUPPORTED.filter((s) => s !== 'internet').map((s) => <option key={s} value={s}>{TYPE_LABELS[s]}</option>)}
              {!SUPPORTED.includes(service.type) && <option value={service.type}>{TYPE_LABELS[service.type] || service.type} (not supported for code)</option>}
            </select>
          </Field>
          {['alb', 'ec2', 'rds', 'lambda'].includes(type) && (
            <Field name="Subnet placement">
              <select value={tier} onChange={(e) => setTier(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
                <option value="unknown">not shown</option><option value="public">public subnet</option><option value="private">private subnet</option>
              </select>
            </Field>
          )}
          {['s3', 'rds', 'dynamodb', 'sqs', 'sns'].includes(type) && <Field name="Encrypted at rest">{tri(encrypted, setEncrypted, 'Encrypted at rest')}</Field>}
          {['s3', 'rds'].includes(type) && <Field name="Publicly accessible">{tri(isPublic, setIsPublic, 'Publicly accessible')}</Field>}
          {type === 'rds' && (
            <>
              <Field name="Multi-AZ">{tri(multiAz, setMultiAz, 'Multi-AZ')}</Field>
              <Field name="Backup retention (days)"><input type="number" min="0" max="35" value={backup} onChange={(e) => setBackup(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" /></Field>
              <Field name="Engine">
                <select value={engine} onChange={(e) => setEngine(e.target.value)} className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
                  <option value="">default (postgres)</option><option value="postgres">PostgreSQL</option><option value="mysql">MySQL</option><option value="mariadb">MariaDB</option>
                </select>
              </Field>
            </>
          )}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit}>Save & re-validate</Button>
        </div>
      </div>
    </div>
  );
}

function IssueCard({ issue, decision, busy, onApply, onAccept, onEdit, onIgnore, onOverride, onUndo }) {
  const [confirming, setConfirming] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const s = SEVERITY[issue.severity];
  const settled = !!decision;
  const critical = issue.severity === 'critical' && issue.source === 'deterministic';
  if (issue.severity === 'valid') {
    return (
      <li className={`rounded-lg border px-4 py-2.5 ${s.box}`} data-issue={issue.id}>
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity="valid" /><SourceTag source={issue.source} />
          <span className="text-sm font-medium text-slate-900">{issue.problem}</span>
        </div>
        <p className="mt-1 text-xs text-slate-600">{issue.reason}</p>
      </li>
    );
  }
  return (
    <li className={`rounded-lg border ${settled ? 'border-slate-200 bg-slate-50 opacity-70' : s.box}`} data-issue={issue.id} data-severity={issue.severity}>
      <div className="flex">
        <div className={`w-1.5 shrink-0 rounded-l-lg ${settled ? 'bg-slate-300' : s.bar}`} />
        <div className="flex-1 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={issue.severity} />
            <SourceTag source={issue.source} />
            {critical && !settled && <span className="text-xs font-semibold text-red-700">Blocks code generation until resolved or overridden</span>}
            {settled && (
              <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-700">
                {decision === 'overridden' ? 'Overridden by you' : decision === 'accepted' ? 'Acknowledged' : 'Ignored'}
              </span>
            )}
          </div>
          <dl className="mt-2 space-y-1.5 text-sm">
            <div><dt className="inline font-semibold text-slate-800">Issue: </dt><dd className="inline text-slate-900">{issue.problem}</dd></div>
            <div><dt className="inline font-semibold text-slate-800">Why: </dt><dd className="inline text-slate-700">{issue.reason}</dd></div>
            <div><dt className="inline font-semibold text-slate-800">Suggested correction: </dt><dd className="inline text-slate-700">{issue.suggestion}</dd></div>
          </dl>
          {!settled && !confirming && (
            <div className="mt-3 flex flex-wrap gap-2">
              {issue.fixes.length > 0 && <Button size="sm" variant="primary" disabled={busy} onClick={() => onApply(issue)}>Apply Correction</Button>}
              {issue.fixes.length === 0 && <Button size="sm" variant="primary" disabled={busy} onClick={() => onAccept(issue)}>Accept Suggestion</Button>}
              {issue.editable && issue.component && <Button size="sm" disabled={busy} onClick={() => onEdit(issue.component)}>Edit</Button>}
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => (critical ? setConfirming(true) : onIgnore(issue))}>Ignore</Button>
            </div>
          )}
          {!settled && confirming && (
            <div className="mt-3 rounded-lg border border-red-300 bg-white p-3 text-sm">
              <p className="font-medium text-red-800">Override this critical issue?</p>
              <p className="mt-1 text-slate-700">The generated infrastructure may be insecure or invalid. This decision is recorded and passed to the code generator and verifier.</p>
              <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} /> I understand the risk</label>
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="danger" disabled={!understood} onClick={() => { onOverride(issue); setConfirming(false); }}>Override and continue</Button>
                <Button size="sm" onClick={() => setConfirming(false)}>Cancel</Button>
              </div>
            </div>
          )}
          {settled && <div className="mt-2"><Button size="sm" variant="ghost" onClick={() => onUndo(issue)}>Undo</Button></div>}
        </div>
      </div>
    </li>
  );
}

export default function IssueList({ issues, decisions, busy, onApply, onAccept, onEdit, onIgnore, onOverride, onUndo, showValid = true }) {
  const open = issues.filter((i) => i.severity !== 'valid');
  const counts = ['critical', 'warning', 'recommendation', 'valid'].map((k) => [k, issues.filter((i) => i.severity === k).length]);
  const shown = showValid ? issues : open;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2" data-testid="issue-counts">
        {counts.map(([k, n]) => (
          <span key={k} className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${SEVERITY[k].badge}`}>{SEVERITY[k].icon} {n} {SEVERITY[k].label}</span>
        ))}
      </div>
      {shown.length === 0 && <p className="text-sm text-slate-500">No issues.</p>}
      <ul className="space-y-2.5">
        {shown.map((i) => (
          <IssueCard key={i.id} issue={i} decision={decisions[i.id]} busy={busy}
            onApply={onApply} onAccept={onAccept} onEdit={onEdit} onIgnore={onIgnore} onOverride={onOverride} onUndo={onUndo} />
        ))}
      </ul>
    </div>
  );
}
