import React, { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { api, ApiError } from './services/api.js';
import { prepareImage } from './services/image.js';
import Stepper, { STEPS, stepIndex } from './components/Stepper.jsx';
import Upload from './components/Upload.jsx';
import Progress from './components/Progress.jsx';
import ArchitectureView from './components/ArchitectureView.jsx';
import IssueList, { EditDialog } from './components/IssueList.jsx';
import Refine, { OPTIONS } from './components/Refine.jsx';
import Requirements from './components/Requirements.jsx';
import Result from './components/Result.jsx';
import Timings from './components/Timings.jsx';
import { Button, Card, ErrorBanner } from './components/ui.jsx';

const initial = {
  phase: 'upload',
  image: null,
  analysis: null,
  arch: null,
  issues: [],
  blocking: [],
  decisions: {},
  refineOptions: [],
  refineText: '',
  lastRefine: null,
  code: {
    formats: { cloudformation: true, cdk: true },
    region: 'ap-south-1',
    environment: 'production',
    prefix: '',
    security: [],
    extra: '',
  },
  gen: null,
  result: null,
  genStage: null,
  timing: { analyze: null, validations: [], generate: null, verify: null },
  reached: {},
  editing: null,
  busy: false,
  validating: false,
  error: null,
};

function reducer(state, action) {
  if (action.type === 'set') return { ...state, ...action.patch };
  if (action.type === 'reset') return { ...initial, code: { ...initial.code } };
  return state;
}

const ANALYZE_MESSAGES = [
  'Uploading and analyzing architecture...',
  'Detecting AWS services...',
  'Reading connections and data flow...',
  'Checking architecture relationships...',
];
const GENERATE_MESSAGES = [
  'Applying your requirements...',
  'Generating Infrastructure as Code...',
  'Validating generated code...',
  'Final verification...',
];

function toError(e, title) {
  if (e instanceof ApiError) {
    const detailsList = e.details && e.details.issues ? e.details.issues.map((i) => i.problem) : null;
    return { title, message: e.message, code: e.code, retryable: e.retryable, detailsList };
  }
  return { title, message: e.message || String(e), code: 'CLIENT_ERROR', retryable: true };
}

export default function App() {
  const [s, dispatch] = useReducer(reducer, initial);
  const set = useCallback((patch) => dispatch({ type: 'set', patch }), []);
  const stateRef = useRef(s);
  stateRef.current = s;
  const [health, setHealth] = React.useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);

  const overrides = useMemo(() => Object.entries(s.decisions).filter(([, v]) => v === 'overridden').map(([k]) => k), [s.decisions]);
  const blocking = useMemo(() => s.blocking.filter((id) => s.decisions[id] !== 'overridden'), [s.blocking, s.decisions]);
  const goto = (phase, extra = {}) => set({ phase, reached: { ...stateRef.current.reached, [stepIndex(phase, null)]: true }, ...extra });

  // ------------------------------------------------------------ upload / analyze
  const onFile = async (file) => {
    try {
      const image = await prepareImage(file);
      set({ image, error: null });
    } catch (e) {
      set({ error: { title: 'This image cannot be used', message: e.message, retryable: false } });
    }
  };

  const analyze = async (force = false) => {
    const img = stateRef.current.image;
    if (!img) return;
    set({ phase: 'analyzing', error: null, busy: true });
    try {
      const { data, roundTripMs } = await api.analyze(img.base64, force);
      set({
        arch: data.architecture, issues: data.issues, blocking: data.blocking, decisions: {}, analysis: { id: data.analysis_id, source: data.source, model: data.model, stored: data.stored_in_s3 },
        timing: { analyze: { server: data.timings, roundTripMs }, validations: [], generate: null, verify: null },
        gen: null, result: null, lastRefine: null, busy: false, phase: 'review', reached: { 0: true, 1: true, 2: true },
      });
    } catch (e) {
      set({ phase: 'upload', busy: false, error: toError(e, e.code === 'NO_COMPONENTS' ? 'Nothing recognisable in this image' : 'Image analysis failed') });
    }
  };

  // ------------------------------------------------------------ architecture edits (all validation happens on the server)
  const applyResult = (data, roundTripMs, extra = {}) => {
    const cur = stateRef.current;
    set({
      arch: data.architecture, issues: data.issues, blocking: data.blocking, busy: false,
      timing: { ...cur.timing, validations: [...cur.timing.validations, data.timings] }, ...extra,
    });
  };

  const runOps = async (ops) => {
    set({ busy: true, error: null });
    try {
      const { data, roundTripMs } = await api.patch(stateRef.current.arch, ops);
      if (data.rejected && data.rejected.length) set({ error: { title: 'Some changes were rejected', message: data.rejected.map((r) => r.reason).join('; '), retryable: false } });
      applyResult(data, roundTripMs);
    } catch (e) {
      set({ busy: false, error: toError(e, 'Could not update the architecture') });
    }
  };

  const decide = (id, kind) => {
    const d = { ...stateRef.current.decisions };
    if (kind) d[id] = kind; else delete d[id];
    set({ decisions: d });
  };

  const runRefine = async () => {
    const cur = stateRef.current;
    set({ busy: true, error: null });
    try {
      const { data, roundTripMs } = await api.refine(cur.arch, cur.refineOptions, cur.refineText);
      applyResult(data, roundTripMs, {
        lastRefine: { applied: data.applied, unmapped: data.unmapped, rejected: data.rejected, interpreter: data.interpreter, warnings: data.warnings },
        refineOptions: [], refineText: '',
      });
      goto('validate');
    } catch (e) {
      set({ busy: false, error: toError(e, 'Refinement could not be applied') });
    }
  };

  const revalidateNow = async () => {
    set({ busy: true, error: null });
    try {
      const { data, roundTripMs } = await api.revalidate(stateRef.current.arch);
      applyResult(data, roundTripMs);
    } catch (e) {
      set({ busy: false, error: toError(e, 'Re-validation failed') });
    }
  };

  // ------------------------------------------------------------ generate + verify
  const generate = async () => {
    const cur = stateRef.current;
    const formats = ['cloudformation', 'cdk'].filter((f) => cur.code.formats[f]);
    const options = { formats, region: cur.code.region, environment: cur.code.environment, prefix: cur.code.prefix, security: cur.code.security, extra: cur.code.extra };
    set({ phase: 'generating', genStage: 'generate', busy: true, error: null, reached: { ...cur.reached, 5: true } });
    const attempt = async () => {
      const g = await api.generate(cur.arch, options, overrides);
      set({ genStage: 'verify' });
      const v = await api.verify(g.data.architecture, g.data.outputs, g.data.options, overrides);
      return { g, v };
    };
    try {
      let out;
      try {
        out = await attempt();
      } catch (e) {
        if (e instanceof ApiError && (e.code === 'ARCH_BLOCKED' || e.code === 'BAD_REGION' || e.code === 'NO_FORMAT' || e.code === 'BAD_ENV')) throw e;
        set({ genStage: 'generate', error: { title: 'Code generation encountered an issue', message: 'Retrying with validated architecture...', retryable: false, code: e.code } });
        out = await attempt(); // second and last automatic attempt
        set({ error: null });
      }
      const { g, v } = out;
      set({
        arch: g.data.architecture, issues: g.data.issues, gen: g.data, result: v.data, busy: false, error: null, phase: 'result',
        timing: { ...stateRef.current.timing, generate: { server: g.data.timings, roundTripMs: g.roundTripMs }, verify: { server: v.data.timings, roundTripMs: v.roundTripMs } },
        reached: { ...stateRef.current.reached, 6: true, 7: true },
      });
    } catch (e) {
      const blockedBack = e instanceof ApiError && e.code === 'ARCH_BLOCKED';
      set({ busy: false, phase: blockedBack ? 'validate' : 'requirements', error: toError(e, blockedBack ? 'The architecture still has critical issues' : 'Code generation failed') });
    }
  };

  const validateFiles = async (fmt) => {
    const cur = stateRef.current;
    set({ validating: true, error: null });
    try {
      const outputs = { [fmt]: { files: cur.result.outputs[fmt].files } };
      const { data } = await api.verify(cur.arch, outputs, { ...cur.gen.options, formats: [fmt] }, overrides);
      const merged = { ...cur.result, outputs: { ...cur.result.outputs, [fmt]: data.outputs[fmt] } };
      merged.verified = Object.values(merged.outputs).every((o) => o.verified);
      merged.security_report = data.security_report;
      set({ result: merged, validating: false });
    } catch (e) {
      set({ validating: false, error: toError(e, 'Validation failed') });
    }
  };

  const onFilesChange = (fmt, files) => {
    const cur = stateRef.current;
    set({ result: { ...cur.result, outputs: { ...cur.result.outputs, [fmt]: { ...cur.result.outputs[fmt], files } } } });
  };

  // ------------------------------------------------------------ issue handlers
  const issueHandlers = {
    busy: s.busy,
    onApply: (issue) => runOps(issue.fixes),
    onAccept: (issue) => decide(issue.id, 'accepted'),
    onEdit: (id) => set({ editing: id }),
    onIgnore: (issue) => decide(issue.id, 'ignored'),
    onOverride: (issue) => decide(issue.id, 'overridden'),
    onUndo: (issue) => decide(issue.id, null),
  };

  const gotoStep = (i) => {
    const map = ['upload', 'analyzing', 'review', 'refine', 'validate', 'requirements'];
    if (i === 1 || !map[i] || !stateRef.current.arch && i > 0) return;
    set({ phase: map[i] });
  };

  const editingService = s.editing && s.arch ? s.arch.services.find((x) => x.id === s.editing) : null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Syntax AI</h1>
          <p className="text-sm text-slate-500">Architecture diagram → reviewed, validated Infrastructure as Code (CloudFormation &amp; CDK)</p>
        </div>
        {s.analysis && s.phase !== 'upload' && (
          <p className="text-xs text-slate-500">Analysis source: <strong>{s.analysis.source}</strong>{s.analysis.model && s.analysis.source === 'bedrock' ? ` (${s.analysis.model})` : ''}</p>
        )}
      </header>

      <Stepper phase={s.phase} genStage={s.genStage} reached={s.reached} onGoto={gotoStep} />

      {s.phase === 'upload' && (
        <Upload image={s.image} onFile={onFile} onAnalyze={() => analyze(false)} error={s.error} onDismissError={() => set({ error: null })} health={health} />
      )}

      {s.phase === 'analyzing' && <Progress title="Analyzing your architecture" messages={ANALYZE_MESSAGES} note="The image is sent to the model once. Every later step works on the structured result." />}

      {s.phase === 'review' && s.arch && (
        <div className="space-y-4">
          <ErrorBanner error={s.error} onDismiss={() => set({ error: null })} />
          <Card title="Detected architecture" subtitle="Review what the AI found. Uncertain items are highlighted, not silently assumed.">
            <ArchitectureView arch={s.arch} issues={s.issues} onOps={runOps} onEdit={(id) => set({ editing: id })} />
          </Card>
          <Card title="Detected problems and ambiguities" subtitle="Each item shows the issue, why it matters and the suggested correction. Critical rule-based issues block code generation until fixed or explicitly overridden.">
            <IssueList issues={s.issues} decisions={s.decisions} {...issueHandlers} />
          </Card>
          <div className="flex items-center justify-between rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-4">
            <p className="text-sm text-indigo-900">Would you like to refine or modify the detected architecture before generating the code?</p>
            <div className="flex gap-2">
              <Button onClick={() => goto('validate')} disabled={s.busy}>No, continue</Button>
              <Button variant="primary" onClick={() => goto('refine')} disabled={s.busy}>Yes, refine</Button>
            </div>
          </div>
        </div>
      )}

      {s.phase === 'refine' && s.arch && (
        <div className="space-y-4">
          <ErrorBanner error={s.error} onRetry={runRefine} onDismiss={() => set({ error: null })} />
          <Refine arch={s.arch} options={s.refineOptions} text={s.refineText} onOptions={(v) => set({ refineOptions: v })} onText={(v) => set({ refineText: v })}
            onApply={runRefine} onSkip={() => goto('validate')} onOps={runOps} busy={s.busy} last={s.lastRefine} />
          {s.busy && <Progress title="Applying your requirements" messages={['Applying your requirements...', 'Checking architecture relationships...']} />}
        </div>
      )}

      {s.phase === 'validate' && s.arch && (
        <div className="space-y-4">
          <ErrorBanner error={s.error} onDismiss={() => set({ error: null })} />
          {s.lastRefine && (s.lastRefine.applied.length > 0 || s.lastRefine.unmapped.length > 0) && (
            <Card title="Changes applied from your refinements">
              {s.lastRefine.applied.length > 0 && <ul className="list-disc pl-5 text-sm text-slate-700">{s.lastRefine.applied.map((a) => <li key={a}>{a}</li>)}</ul>}
              {s.lastRefine.unmapped.length > 0 && <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900">Not applied automatically: {s.lastRefine.unmapped.join('; ')}</p>}
            </Card>
          )}
          <Card title="Architecture validation" subtitle="The corrected architecture has been re-validated. Resolve or override every critical issue to continue."
            right={<Button size="sm" onClick={revalidateNow} disabled={s.busy}>Re-run validation</Button>}>
            <ArchitectureView arch={s.arch} issues={s.issues} onOps={runOps} onEdit={(id) => set({ editing: id })} />
            <div className="mt-5"><IssueList issues={s.issues} decisions={s.decisions} {...issueHandlers} /></div>
          </Card>
          <div className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-5 py-4 ${blocking.length ? 'border-red-300 bg-red-50' : 'border-emerald-300 bg-emerald-50'}`}>
            <p className={`text-sm ${blocking.length ? 'text-red-900' : 'text-emerald-900'}`} data-testid="confirm-status">
              {blocking.length ? `${blocking.length} critical issue(s) must be fixed or overridden before code can be generated.` : '✓ Architecture validated. Confirm it to continue to code requirements.'}
              {overrides.length > 0 && ` (${overrides.length} override${overrides.length > 1 ? 's' : ''} recorded)`}
            </p>
            <div className="flex gap-2">
              <Button onClick={() => goto('refine')} disabled={s.busy}>Back to refine</Button>
              <Button variant="primary" disabled={blocking.length > 0 || s.busy} onClick={() => goto('requirements')}>Confirm architecture</Button>
            </div>
          </div>
        </div>
      )}

      {s.phase === 'requirements' && s.arch && (
        <div className="space-y-4">
          <ErrorBanner error={s.error} onRetry={generate} onDismiss={() => set({ error: null })} />
          <Requirements code={s.code} onChange={(code) => set({ code })} arch={s.arch} onGenerate={generate} onBack={() => goto('validate')} busy={s.busy} />
        </div>
      )}

      {s.phase === 'generating' && (
        <div className="space-y-4">
          {s.error && <ErrorBanner error={s.error} />}
          <Progress title={s.genStage === 'verify' ? 'Verifying generated code' : 'Generating Infrastructure as Code'} messages={GENERATE_MESSAGES} activeIndex={s.genStage === 'verify' ? 2 : 1}
            note="Code is generated from the confirmed structured architecture (no image, no extra model round trips), then validated and auto-corrected." />
        </div>
      )}

      {s.phase === 'result' && s.result && (
        <div>
          <ErrorBanner error={s.error} onDismiss={() => set({ error: null })} />
          <Result result={s.result} gen={s.gen} onFilesChange={onFilesChange} onValidate={validateFiles} validating={s.validating}
            onRestart={() => dispatch({ type: 'reset' })} onBackToRequirements={() => goto('requirements')}
            timings={<Timings timing={s.timing} source={s.analysis && s.analysis.source} />} source={s.analysis && s.analysis.source} />
        </div>
      )}

      {editingService && <EditDialog service={editingService} onClose={() => set({ editing: null })} onApply={(ops) => { set({ editing: null }); if (ops.length) runOps(ops); }} />}
    </div>
  );
}
