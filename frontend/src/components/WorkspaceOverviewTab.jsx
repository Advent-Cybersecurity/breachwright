import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BookOpen, ClipboardList, FileCheck2, FileText, RotateCcw, Server, ShieldCheck, Target, Upload } from 'lucide-react';

import { checklists as checklistApi, evidenceNotebook as notebookApi, workflow as workflowApi } from '../api';
import { SeverityBadge, Spinner } from './UI';


function MetricCard({ label, value, detail, icon: Icon, onClick, tone = 'themed-text-primary' }) {
  const content = (
    <>
      <div className="flex items-center justify-between gap-3">
        <Icon size={16} className="themed-text-muted" />
        <span className={`text-2xl font-mono ${tone}`}>{value}</span>
      </div>
      <div className="text-sm font-medium themed-text-primary mt-3">{label}</div>
      <div className="text-xs themed-text-muted mt-1">{detail}</div>
    </>
  );
  return onClick ? (
    <button className="card p-4 text-left hover:border-red-500/40 transition-colors" onClick={onClick}>{content}</button>
  ) : (
    <div className="card p-4">{content}</div>
  );
}


export default function WorkspaceOverviewTab({ engId, findings, toast, onOpenTab }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [readiness, retests, assets, checklistProgress, snapshots, notebook] = await Promise.all([
      workflowApi.readiness(engId),
      workflowApi.retestOverview(engId),
      workflowApi.assets(engId),
      checklistApi.progress(engId),
      workflowApi.listSnapshots(engId),
      notebookApi.list(engId),
    ]);
    setData({ readiness, retests, assets, checklistProgress, snapshots, notebook });
  }, [engId]);

  useEffect(() => {
    load()
      .catch(err => toast({ message: `Workspace overview could not be loaded: ${err.message}`, type: 'error' }))
      .finally(() => setLoading(false));
  }, [load, toast]);

  const checklist = useMemo(() => {
    const rows = Object.values(data?.checklistProgress || {});
    const total = rows.reduce((sum, item) => sum + (item.total || 0), 0);
    const done = rows.reduce((sum, item) => sum + (item.done || 0), 0);
    return { total, done, percent: total ? Math.round((done / total) * 100) : 0 };
  }, [data]);

  if (loading) return <div className="flex justify-center py-16"><Spinner className="w-6 h-6 themed-text-muted" /></div>;
  if (!data) return null;

  const highRisk = findings.filter(finding => ['critical', 'high'].includes(finding.severity));
  const activeRetests = data.retests.summary.overdue + data.retests.summary.due_soon + data.retests.summary.unscheduled + data.retests.summary.scheduled;
  const unreviewedNotes = data.readiness.summary.unreviewed_evidence_notes || 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold themed-text-primary">Workspace Overview</h2>
          <p className="text-sm themed-text-muted">Current local assessment state and the work most likely to need attention.</p>
        </div>
        <button className="btn-secondary text-sm" onClick={() => onOpenTab('reports')}>Open Report Readiness</button>
      </div>

      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <MetricCard label="Findings" value={findings.length}
          detail={`${highRisk.length} critical or high`} icon={Target} onClick={() => onOpenTab('findings')}
          tone={highRisk.length ? 'text-severity-high' : 'themed-text-primary'} />
        <MetricCard label="Current assets" value={data.assets.summary.assets}
          detail={`${data.assets.summary.services} services in latest snapshot`} icon={Server} onClick={() => onOpenTab('assets')} />
        <MetricCard label="Active retests" value={activeRetests}
          detail={`${data.retests.summary.overdue} overdue`} icon={RotateCcw} onClick={() => onOpenTab('retests')}
          tone={data.retests.summary.overdue ? 'text-red-400' : 'themed-text-primary'} />
        <MetricCard label="Report readiness" value={data.readiness.score}
          detail={`${data.readiness.blockers.length} blockers, ${data.readiness.warnings.length} warnings`}
          icon={data.readiness.ready ? ShieldCheck : AlertTriangle} onClick={() => onOpenTab('reports')}
          tone={data.readiness.ready ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Checklist progress" value={`${checklist.percent}%`}
          detail={`${checklist.done} of ${checklist.total} complete`} icon={ClipboardList} onClick={() => onOpenTab('checklists')} />
        <MetricCard label="Evidence notes" value={data.notebook.total}
          detail={`${unreviewedNotes} not yet reviewed into Findings`} icon={BookOpen} onClick={() => onOpenTab('notebook')}
          tone={unreviewedNotes ? 'text-yellow-400' : 'themed-text-primary'} />
        <MetricCard label="Scan snapshots" value={data.snapshots.length}
          detail={data.snapshots[0] ? `Latest: ${data.snapshots[0].label}` : 'No baseline yet'} icon={Upload} onClick={() => onOpenTab('scans')} />
        <MetricCard label="Snapshot parser" value={data.snapshots[0]?.parser_version || 'None'}
          detail="Normalization version for the latest snapshot" icon={FileCheck2} />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <RotateCcw size={15} className="themed-text-muted" />
            <h3 className="text-sm font-semibold themed-text-primary">Retest priorities</h3>
          </div>
          {data.retests.overdue.length === 0 && data.retests.due_soon.length === 0 ? (
            <p className="text-xs themed-text-muted">No overdue or due-soon retests.</p>
          ) : (
            <div className="space-y-2">
              {[...data.retests.overdue, ...data.retests.due_soon].slice(0, 5).map(finding => (
                <button key={finding.id} className="w-full rounded border p-2 flex items-center gap-2 text-left"
                  style={{ borderColor: 'var(--border)' }} onClick={() => onOpenTab('retests')}>
                  <SeverityBadge severity={finding.severity} />
                  <span className="text-xs themed-text-secondary flex-1 truncate">{finding.title}</span>
                  <span className="text-[10px] font-mono themed-text-muted">{finding.retest_due_date}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <FileText size={15} className="themed-text-muted" />
            <h3 className="text-sm font-semibold themed-text-primary">Readiness review</h3>
          </div>
          {data.readiness.blockers.length === 0 && data.readiness.warnings.length === 0 ? (
            <p className="text-xs text-green-400">No readiness issues are recorded.</p>
          ) : (
            <div className="space-y-2">
              {[...data.readiness.blockers, ...data.readiness.warnings].slice(0, 6).map(item => (
                <div key={item.code} className="text-xs rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                  <span className={data.readiness.blockers.includes(item) ? 'text-red-400' : 'text-yellow-400'}>
                    {data.readiness.blockers.includes(item) ? 'Blocker' : 'Warning'}:
                  </span>{' '}
                  <span className="themed-text-secondary">{item.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
