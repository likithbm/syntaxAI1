import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Check, SEVERITY } from './ui.jsx';
import { highlight } from '../services/highlight.js';
import { copyText, downloadFile, downloadZip } from '../services/files.js';

function useFlash() {
  const [msg, setMsg] = useState('');
  const t = useRef(null);
  const flash = (m) => { setMsg(m); clearTimeout(t.current); t.current = setTimeout(() => setMsg(''), 2500); };
  useEffect(() => () => clearTimeout(t.current), []);
  return [msg, flash];
}

export function CopyButton({ text, label = 'Copy Code', size = 'md', variant = 'primary' }) {
  const [msg, flash] = useFlash();
  return (
    <span className="inline-flex items-center gap-2">
      <Button size={size} variant={variant} onClick={async () => flash((await copyText(text)) ? '✓ Code copied successfully' : 'Copy failed - select the code and press Ctrl+C')}>{label}</Button>
      <span role="status" aria-live="polite" className={`text-xs font-medium ${msg.startsWith('✓') ? 'text-emerald-700' : 'text-red-700'}`}>{msg}</span>
    </span>
  );
}

function CodeViewer({ file, editing, onEdit }) {
  const html = useMemo(() => highlight(file.content, file.language), [file.content, file.language]);
  const lines = file.content.split('\n').length;
  if (editing) {
    return (
      <textarea aria-label={`Edit ${file.path}`} value={file.content} onChange={(e) => onEdit(e.target.value)} spellCheck={false}
        className="mono block h-[28rem] w-full resize-y rounded-b-lg bg-slate-900 p-4 text-[13px] leading-5 text-slate-100 focus:outline-none" />
    );
  }
  return (
    <div className="flex max-h-[32rem] overflow-auto rounded-b-lg bg-slate-900 text-[13px] leading-5" data-testid="code-viewer">
      <pre aria-hidden="true" className="mono select-none border-r border-slate-700 px-3 py-4 text-right text-slate-500">{Array.from({ length: lines }, (_, i) => i + 1).join('\n')}</pre>
      <pre className="mono flex-1 px-4 py-4 text-slate-100"><code dangerouslySetInnerHTML={{ __html: html }} /></pre>
    </div>
  );
}

function List({ items }) {
  return <ul className="list-disc space-y-0.5 pl-5">{items.map((x) => <li key={x}>{x}</li>)}</ul>;
}

function Info({ meta, file }) {
  return (
    <Card title="Deployment details" subtitle="Everything needed to run this exact output">
      <dl className="grid gap-x-6 gap-y-3 text-sm md:grid-cols-2">
        <div><dt className="font-semibold text-slate-800">File name</dt><dd className="mono text-slate-700">{file.path}</dd></div>
        <div><dt className="font-semibold text-slate-800">Language</dt><dd className="text-slate-700">{meta.title} ({file.language})</dd></div>
        <div><dt className="font-semibold text-slate-800">AWS region</dt><dd className="mono text-slate-700">{meta.aws_region}</dd></div>
        <div><dt className="font-semibold text-slate-800">Configuration requirements</dt><dd className="text-slate-700"><List items={meta.configuration} /></dd></div>
        <div><dt className="font-semibold text-slate-800">Required dependencies</dt><dd className="text-slate-700"><List items={meta.dependencies} /></dd></div>
        <div><dt className="font-semibold text-slate-800">Environment variables</dt><dd className="text-slate-700"><List items={meta.environment_variables} /></dd></div>
        <div><dt className="font-semibold text-slate-800">Prerequisites</dt><dd className="text-slate-700"><List items={meta.prerequisites} /></dd></div>
        <div><dt className="font-semibold text-slate-800">Stack parameters</dt><dd className="text-slate-700">{meta.parameters.length ? <List items={meta.parameters} /> : 'none required'}</dd></div>
        <div className="md:col-span-2"><dt className="font-semibold text-slate-800">IAM permissions required to deploy</dt><dd className="text-slate-700"><List items={meta.iam_permissions} /></dd></div>
        <div className="md:col-span-2">
          <dt className="font-semibold text-slate-800">Deployment command</dt>
          <dd className="mt-1 flex items-start gap-2"><code className="mono block flex-1 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2 text-xs text-slate-100">{meta.deployment_command}</code><CopyButton text={meta.deployment_command} label="Copy" size="sm" variant="secondary" /></dd>
        </div>
      </dl>
    </Card>
  );
}

function RunGuide({ meta }) {
  return (
    <Card title="How to Run" subtitle={meta.format === 'cdk' ? 'AWS CDK (TypeScript) - these commands match the generated project' : 'CloudFormation - these commands match the generated template'}>
      <ol className="space-y-4">
        {meta.steps.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">{s.title}</p>
              {s.detail && <pre className="mono mt-1 whitespace-pre-wrap text-xs text-slate-600">{s.detail}</pre>}
              {s.commands.map((c) => (
                <div key={c} className="mt-2 flex items-start gap-2">
                  <code className="mono block flex-1 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2 text-xs text-slate-100">{c}</code>
                  {!c.startsWith('#') && <CopyButton text={c} label="Copy" size="sm" variant="secondary" />}
                </div>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Validation({ out }) {
  const findings = out.findings.filter((f) => f.severity !== 'info');
  return (
    <Card title="Code validation" subtitle="Deterministic checks run on the generated code before it is shown as final"
      right={<span className={`rounded-full px-3 py-1 text-xs font-semibold ${out.verified ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>{out.verified ? '✓ Verified' : '✕ Not verified'}</span>}>
      <ul className="grid gap-1.5 sm:grid-cols-2" data-testid="checks">
        {out.checks.map((c) => (
          <li key={c.name} className="flex items-center gap-2 text-sm"><Check status={c.status} /> {c.name}</li>
        ))}
      </ul>
      {out.fix_log.length > 0 && (
        <div className="mt-3 rounded-lg bg-sky-50 p-3 text-sm text-sky-900">
          <p className="font-semibold">Automatically corrected and re-validated ({out.rounds} round{out.rounds === 1 ? '' : 's'})</p>
          <ul className="list-disc pl-5">{out.fix_log.flatMap((r) => (r.applied.length ? r.applied : [r.note || 'no automatic fix available']).map((a) => <li key={r.round + a}>{a} <span className="text-xs text-sky-700">({r.how === 'ai' ? 'AI fix' : 'rule-based fix'})</span></li>))}</ul>
        </div>
      )}
      {findings.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b text-xs uppercase text-slate-500"><th className="py-1 pr-3">Severity</th><th className="py-1 pr-3">Finding</th><th className="py-1">File</th></tr></thead>
            <tbody>
              {findings.map((f, i) => (
                <tr key={f.key + i} className="border-b border-slate-100 align-top">
                  <td className="py-1.5 pr-3 whitespace-nowrap">{SEVERITY[f.severity] ? SEVERITY[f.severity].icon : ''} {f.severity}{f.overridden ? ' (overridden)' : ''}</td>
                  <td className="py-1.5 pr-3">{f.message}<div className="mono text-[11px] text-slate-400">{f.code}</div></td>
                  <td className="mono py-1.5 text-xs">{f.file}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {out.checks.some((c) => c.name.includes('TypeScript')) && (
        <p className="mt-3 text-xs text-slate-500">TypeScript checks here are structural (syntax balance, imports, constructs, identifiers). The final authority is <code className="mono">npx cdk synth</code>, which the run guide includes.</p>
      )}
      {out.meta.format === 'cloudformation' && (
        <p className="mt-3 text-xs text-slate-500">The template is checked against a built-in resource model. Optionally run <code className="mono">cfn-lint template.yaml</code>; <code className="mono">aws cloudformation validate-template</code> is step 4 of the run guide.</p>
      )}
    </Card>
  );
}

function Security({ report }) {
  return (
    <Card title="Security review" subtitle="Deterministic validation, AI recommendations and your own requirements are reported separately">
      <h3 className="mb-2 text-sm font-semibold text-slate-800">Deterministic validation (fixed rules, run on the generated code)</h3>
      <table className="w-full text-sm" data-testid="security-rows">
        <tbody>
          {report.deterministic.map((r) => (
            <tr key={r.category} className="border-b border-slate-100 align-top">
              <td className="w-8 py-1.5"><Check status={r.status} /></td>
              <td className="py-1.5 pr-3 font-medium">{r.category}</td>
              <td className="py-1.5 text-slate-600">{r.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold text-slate-800">AI recommendations <span className="font-normal text-slate-500">(advisory, from the image)</span></h3>
          {report.ai_advisory.length === 0 ? <p className="text-sm text-slate-500">None reported.</p> : (
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{report.ai_advisory.map((a, i) => <li key={i}>{a.message}{a.component ? <span className="text-xs text-slate-400"> ({a.component})</span> : null}</li>)}</ul>
          )}
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold text-slate-800">Your selected requirements</h3>
          {report.user_requirements.length + report.user_notes.length === 0 ? <p className="text-sm text-slate-500">None selected.</p> : (
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
              {report.user_requirements.map((r) => <li key={r}>{r.replace(/_/g, ' ')}</li>)}
              {report.user_notes.map((n) => <li key={n}>{n} <span className="text-xs text-slate-400">(note - not machine-enforced)</span></li>)}
            </ul>
          )}
        </div>
      </div>
      <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">{report.disclaimer}</p>
    </Card>
  );
}

export default function Result({ result, gen, onFilesChange, onValidate, validating, onRestart, onBackToRequirements, timings, source }) {
  const formats = Object.keys(result.outputs);
  const [fmt, setFmt] = useState(formats[0]);
  const out = result.outputs[fmt] || result.outputs[formats[0]];
  const [sel, setSel] = useState(0);
  const [editing, setEditing] = useState(false);
  useEffect(() => { setSel(0); setEditing(false); }, [fmt]);
  const file = out.files[Math.min(sel, out.files.length - 1)];
  const edit = (content) => onFilesChange(fmt, out.files.map((f) => (f.path === file.path ? { ...f, content } : f)));
  const Timings = timings;
  return (
    <div className="space-y-4">
      <div className={`rounded-xl border p-4 ${result.verified ? 'border-emerald-300 bg-emerald-50' : 'border-red-300 bg-red-50'}`} role="status">
        <p className={`text-base font-semibold ${result.verified ? 'text-emerald-900' : 'text-red-900'}`}>
          {result.verified ? '✓ Final code verified - it passed all validation checks' : '✕ Code is NOT verified - review the findings below before using it'}
        </p>
        {gen && gen.notes && gen.notes.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-slate-800">{gen.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {gen && gen.skipped_components && gen.skipped_components.length > 0 && <p className="mt-2 text-sm text-amber-900">Not included in the code (unsupported service): {gen.skipped_components.join(', ')}</p>}
        {gen && gen.unmapped && gen.unmapped.length > 0 && <p className="mt-2 text-sm text-amber-900">Requirements that could not be applied automatically: {gen.unmapped.join('; ')}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {formats.map((f) => (
          <button key={f} type="button" onClick={() => setFmt(f)} className={`rounded-lg px-4 py-2 text-sm font-medium ${f === fmt ? 'bg-indigo-600 text-white' : 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50'}`}>
            {result.outputs[f].meta.title}
          </button>
        ))}
        {out.meta.format === 'cdk' && <Button variant="secondary" onClick={() => downloadZip(out.files, 'syntax-ai-cdk', 'syntax-ai-cdk.zip')}>Download project (.zip)</Button>}
      </div>

      {out.meta.format === 'cdk' && (
        <Card title="Generated project structure"><pre className="mono text-sm text-slate-700" data-testid="tree">{out.meta.tree}</pre></Card>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {out.files.length > 1 && (
              <select aria-label="Select file" value={sel} onChange={(e) => { setSel(Number(e.target.value)); setEditing(false); }} className="rounded-lg border border-slate-300 px-2 py-1 text-sm">
                {out.files.map((f, i) => <option key={f.path} value={i}>{f.path}</option>)}
              </select>
            )}
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">File</p>
              <p className="mono text-sm font-semibold" data-testid="file-name">{file.path}</p>
            </div>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{file.language}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <CopyButton text={file.content} />
            <Button onClick={() => downloadFile(file.path, file.content)}>Download File</Button>
            <Button onClick={() => setEditing((e) => !e)} variant="ghost">{editing ? 'Done editing' : 'Edit'}</Button>
            <Button disabled={validating} onClick={() => onValidate(fmt)}>{validating ? 'Validating…' : 'Validate'}</Button>
          </div>
        </div>
        <CodeViewer file={file} editing={editing} onEdit={edit} />
      </section>

      <Validation out={out} />
      <RunGuide meta={out.meta} />
      <Info meta={out.meta} file={file} />
      <Security report={result.security_report} />
      {Timings}
      <div className="flex justify-between pb-8">
        <Button onClick={onBackToRequirements}>Change requirements & regenerate</Button>
        <Button onClick={onRestart}>Start over with a new diagram</Button>
      </div>
    </div>
  );
}
