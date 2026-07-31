import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, BookOpen, ClipboardList, FileCheck2, FileText, RefreshCw, RotateCcw, Server, ShieldCheck, Target, Upload } from 'lucide-react';

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
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const labels = ['readiness', 'retests', 'assets', 'checklists', 'snapshots', 'notebook', 'activity'];
    const results = await Promise.allSettled([
      workflowApi.readiness(engId), workflowApi.retestOverview(engId),
      workflowApi.assets(engId), checklistApi.progress(engId),
      workflowApi.listSnapshots(engId), notebookApi.list(engId),
      workflowApi.activity(engId),
    ]);
    const failed = results.flatMap((result, index) => result.status === 'rejected' ? [labels[index]] : []);
    setData(previous => ({
      readiness: results[0].status === 'fulfilled' ? results[0].value : previous?.readiness || {
        score: 0, ready: false,
        blockers: [{ code: 'overview_readiness_unavailable', message: 'Report readiness could not be loaded.' }],
        warnings: [], summary: { unreviewed_evidence_notes: 0 },
      },
      retests: results[1].status === 'fulfilled' ? results[1].value : previous?.retests || {
        summary: { overdue: 0, due_soon: 0, unscheduled: 0, scheduled: 0 },
        overdue: [], due_soon: [],
      },
      assets: results[2].status === 'fulfilled' ? results[2].value : previous?.assets || { summary: { assets: 0, services: 0 } },
      checklistProgress: results[3].status === 'fulfilled' ? results[3].value : previous?.checklistProgress || {},
      snapshots: results[4].status === 'fulfilled' ? results[4].value : previous?.snapshots || [],
      notebook: results[5].status === 'fulfilled' ? results[5].value : previous?.notebook || { total: 0, notes: [] },
      activity: results[6].status === 'fulfilled' ? results[6].value : previous?.activity || { count: 0, events: [] },
    }));
    if (failed.length) {
      toast({ message: `Overview loaded with unavailable sections: ${failed.join(', ')}`, type: 'error' });
    }
  }, [engId, toast]);

  useEffect(() => {
    load().finally(() => setLoading(false));
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
        <div className="flex gap-2">
          <button className="btn-secondary text-sm flex items-center gap-2" disabled={refreshing} onClick={async () => {
            setRefreshing(true);
            try { await load(); } finally { setRefreshing(false); }
          }}>
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
          <button className="btn-secondary text-sm" onClick={() => onOpenTab('reports')}>Open Report Readiness</button>
        </div>
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

      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={15} className="themed-text-muted" />
          <h3 className="text-sm font-semibold themed-text-primary">Recent workspace activity</h3>
        </div>
        {data.activity.events.length === 0 ? (
          <p className="text-xs themed-text-muted">Activity appears here as assessment records are created or updated.</p>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {data.activity.events.slice(0, 10).map(event => (
              <button key={`${event.kind}-${event.id}`} className="w-full py-2 flex items-center gap-3 text-left hover:bg-white/[0.02]"
                onClick={() => onOpenTab(event.tab)}>
                <span className="badge shrink-0">{event.kind.replace('_', ' ')}</span>
                <span className="text-xs themed-text-primary truncate flex-1">{event.title}</span>
                <span className="hidden sm:block text-[10px] themed-text-muted">{event.detail}</span>
                <time className="text-[10px] font-mono themed-text-muted shrink-0" dateTime={event.timestamp}>
                  {new Date(event.timestamp).toLocaleString()}
                </time>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
