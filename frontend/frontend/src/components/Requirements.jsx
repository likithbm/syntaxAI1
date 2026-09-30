import React from 'react';
import { Button, Card } from './ui.jsx';
import { OptionChecks } from './Refine.jsx';

export const REGIONS = [
  ['ap-south-1', 'Asia Pacific (Mumbai) ap-south-1'], ['ap-south-2', 'Asia Pacific (Hyderabad) ap-south-2'],
  ['ap-southeast-1', 'Asia Pacific (Singapore) ap-southeast-1'], ['ap-southeast-2', 'Asia Pacific (Sydney) ap-southeast-2'],
  ['ap-northeast-1', 'Asia Pacific (Tokyo) ap-northeast-1'], ['ap-northeast-2', 'Asia Pacific (Seoul) ap-northeast-2'],
  ['us-east-1', 'US East (N. Virginia) us-east-1'], ['us-east-2', 'US East (Ohio) us-east-2'],
  ['us-west-1', 'US West (N. California) us-west-1'], ['us-west-2', 'US West (Oregon) us-west-2'],
  ['ca-central-1', 'Canada (Central) ca-central-1'], ['sa-east-1', 'South America (Sao Paulo) sa-east-1'],
  ['eu-central-1', 'Europe (Frankfurt) eu-central-1'], ['eu-west-1', 'Europe (Ireland) eu-west-1'],
  ['eu-west-2', 'Europe (London) eu-west-2'], ['eu-west-3', 'Europe (Paris) eu-west-3'], ['eu-north-1', 'Europe (Stockholm) eu-north-1'],
];

export default function Requirements({ code, onChange, arch, onGenerate, onBack, busy }) {
  const set = (patch) => onChange({ ...code, ...patch });
  const fmts = code.formats;
  const toggleSec = (id) => set({ security: code.security.includes(id) ? code.security.filter((x) => x !== id) : [...code.security, id] });
  const any = fmts.cloudformation || fmts.cdk;
  return (
    <Card title="Code Generation Requirements" subtitle="What requirements or refinements should be applied to the generated Infrastructure as Code?">
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-800">Output</h3>
          <label className="mb-1.5 flex items-center gap-2 text-sm"><input type="checkbox" checked={fmts.cloudformation} onChange={(e) => set({ formats: { ...fmts, cloudformation: e.target.checked } })} /> CloudFormation YAML</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={fmts.cdk} onChange={(e) => set({ formats: { ...fmts, cdk: e.target.checked } })} /> AWS CDK TypeScript <span className="text-xs text-slate-500">(project: package.json, cdk.json, bin/, lib/)</span></label>
          {!any && <p className="mt-1 text-xs text-red-700">Select at least one output.</p>}
          <p className="mt-2 text-xs text-slate-500">CDK language: TypeScript (the only CDK language generated in this version).</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1">
          <label className="block text-sm"><span className="mb-1 block font-semibold text-slate-800">AWS Region</span>
            <select value={code.region} onChange={(e) => set({ region: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm">
              {REGIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="block text-sm"><span className="mb-1 block font-semibold text-slate-800">Environment</span>
            <select value={code.environment} onChange={(e) => set({ environment: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2 py-2 text-sm">
              <option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option>
            </select>
          </label>
        </div>
        <label className="block text-sm md:col-span-2"><span className="mb-1 block font-semibold text-slate-800">Resource naming convention</span>
          <input value={code.prefix} onChange={(e) => set({ prefix: e.target.value })} placeholder={`Prefix for the stack and Name tags, e.g. myapp-${code.environment} (lower-case letters, digits, hyphens)`} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        </label>
      </div>
      <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-800">Security, availability and cost requirements</h3>
      <OptionChecks selected={code.security} onToggle={toggleSec} />
      <p className="mt-2 text-xs text-slate-500">IAM least privilege, security groups, S3 public-access blocking and TLS-only bucket policies are always applied. Production also enables deletion protection, retention policies and 7-day database backups.</p>
      <label className="mt-4 block text-sm"><span className="mb-1 block font-semibold text-slate-800">Additional requirements</span>
        <textarea rows={3} value={code.extra} onChange={(e) => set({ extra: e.target.value })} placeholder="Example: production-ready, high availability, encryption, backups, logging, least-privilege IAM, cost optimization"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200" />
      </label>
      <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
        Confirmed architecture: <strong>{arch.services.filter((s) => s.type !== 'internet').length}</strong> components, <strong>{arch.connections.length}</strong> connections, <strong>{arch.network.availability_zones}</strong> AZ(s). Code is generated only from this validated architecture.
      </div>
      <div className="mt-5 flex justify-between">
        <Button onClick={onBack} disabled={busy}>Back</Button>
        <Button variant="primary" onClick={onGenerate} disabled={busy || !any}>Confirm & generate code</Button>
      </div>
    </Card>
  );
}
