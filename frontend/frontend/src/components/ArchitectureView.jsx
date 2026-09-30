import React, { useState } from 'react';
import { Button, Card } from './ui.jsx';

export const TYPE_LABELS = {
  alb: 'Application Load Balancer', ec2: 'EC2', rds: 'RDS', s3: 'S3', lambda: 'Lambda', dynamodb: 'DynamoDB', sqs: 'SQS', sns: 'SNS',
  internet: 'Internet', api_gateway: 'API Gateway', cloudfront: 'CloudFront', route53: 'Route 53', waf: 'WAF', cognito: 'Cognito',
  ecs: 'ECS', eks: 'EKS', elasticache: 'ElastiCache', efs: 'EFS', kinesis: 'Kinesis', cloudwatch: 'CloudWatch', iam_role: 'IAM role', other: 'Unknown',
};
export const SUPPORTED = ['alb', 'ec2', 'rds', 's3', 'lambda', 'dynamodb', 'sqs', 'sns', 'internet'];

const ICON = { alb: '⚖️', ec2: '🖥️', rds: '🗄️', s3: '🪣', lambda: 'λ', dynamodb: '📚', sqs: '📨', sns: '📣', internet: '🌐', other: '❓' };

function issueFor(issues, id) {
  const list = (issues || []).filter((i) => i.component === id && i.severity !== 'valid');
  const order = ['critical', 'warning', 'recommendation'];
  return order.find((s) => list.some((i) => i.severity === s)) || null;
}

const RING = { critical: 'ring-2 ring-red-400', warning: 'ring-2 ring-orange-300', recommendation: 'ring-1 ring-yellow-300' };

export default function ArchitectureView({ arch, issues, onOps, onEdit, editable = true }) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const net = arch.network;
  const ids = arch.services.map((s) => s.id);
  const label = (id) => (arch.services.find((s) => s.id === id) || { label: id }).label;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Detected services" subtitle={`${arch.services.length} component${arch.services.length === 1 ? '' : 's'} detected`}>
        <ul className="space-y-2" data-testid="services">
          {net.vpc && (
            <li className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <span aria-hidden="true">☁️</span>
              <span className="font-medium">VPC</span>
              <span className="text-xs text-slate-500">{net.vpc_cidr || 'CIDR not shown (10.0.0.0/16 will be used)'} • {net.availability_zones} Availability Zone{net.availability_zones === 1 ? '' : 's'}</span>
            </li>
          )}
          {net.subnets.map((s) => (
            <li key={s.id} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <span aria-hidden="true">🧱</span>
              <span className="font-medium capitalize">{s.tier === 'unknown' ? 'Subnet' : `${s.tier} subnet`}</span>
              <span className="text-xs text-slate-500">{s.id}</span>
            </li>
          ))}
          {arch.services.map((s) => {
            const sev = issueFor(issues, s.id);
            const unsure = s.type === 'other' || s.confidence < 0.6;
            return (
              <li key={s.id} className={`flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 text-sm ${sev ? RING[sev] : ''}`} data-component={s.id}>
                <span className="w-6 text-center text-lg" aria-hidden="true">{ICON[s.type] || '📦'}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{s.label}</span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{TYPE_LABELS[s.type] || s.type}</span>
                    {s.tier !== 'n/a' && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{s.tier === 'unknown' ? 'placement not shown' : `${s.tier} subnet`}</span>}
                    {unsure && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[11px] text-orange-800">{Math.round(s.confidence * 100)}% sure</span>}
                  </div>
                  <div className="mono truncate text-[11px] text-slate-400">{s.id}</div>
                </div>
                {editable && s.type !== 'internet' && <Button size="sm" variant="ghost" onClick={() => onEdit(s.id)}>Edit</Button>}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card title="Detected connections" subtitle="Direction follows the arrows in the diagram">
        <ul className="space-y-1.5" data-testid="connections">
          {arch.connections.length === 0 && <li className="text-sm text-slate-500">No connections were detected.</li>}
          {arch.connections.map((c) => {
            const bad = c.unresolved;
            return (
              <li key={`${c.from}->${c.to}`} className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${bad ? 'bg-red-50 ring-1 ring-red-300' : 'bg-slate-50'}`}>
                <span className="font-medium">{label(c.from)}</span>
                <span aria-hidden="true" className="text-slate-400">→</span>
                <span className="sr-only">to</span>
                <span className="font-medium">{label(c.to)}</span>
                {c.label && <span className="text-xs text-slate-500">({c.label})</span>}
                {bad && <span className="text-xs text-red-700">unknown endpoint</span>}
                {editable && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onOps([{ op: 'remove_connection', from: c.from, to: c.to }])} aria-label={`Remove connection ${c.from} to ${c.to}`}>Remove</Button>}
              </li>
            );
          })}
        </ul>
        {editable && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <select aria-label="Connection source" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1 text-sm">
              <option value="">from…</option>
              {ids.map((i) => <option key={i} value={i}>{label(i)}</option>)}
            </select>
            <span aria-hidden="true">→</span>
            <select aria-label="Connection target" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1 text-sm">
              <option value="">to…</option>
              {ids.map((i) => <option key={i} value={i}>{label(i)}</option>)}
            </select>
            <Button size="sm" disabled={!from || !to || from === to} onClick={() => { onOps([{ op: 'add_connection', from, to }]); setFrom(''); setTo(''); }}>Add connection</Button>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Image quality: <strong>{arch.image_quality}</strong>{arch.image_quality_notes ? ` - ${arch.image_quality_notes}` : ''}
        </p>
      </Card>
    </div>
  );
}
