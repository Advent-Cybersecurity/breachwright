import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  engagements as engApi, findings as findingsApi, analysis as analysisApi,
  attackPaths as apApi, reports as reportsApi, evidence as evidenceApi,
  narratives as narrativeApi,
  exportImport, ad as adApi, reportTemplates as templatesApi, workflow as workflowApi,
  findingTemplates as findingTemplatesApi
} from '../api';
import { Modal, SeverityBadge, StatusBadge, EmptyState, SectionHeader, Toast, Spinner } from '../components/UI';
import ADPathGraph from '../components/ADPathGraph';
import ChecklistsTab from '../components/ChecklistsTab';
import GapAnalysisTab from '../components/GapAnalysisTab';
import EvidenceNotebookTab from '../components/EvidenceNotebookTab';
import WorkspaceOverviewTab from '../components/WorkspaceOverviewTab';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  ArrowLeft, Plus, Upload, Zap, Route, FileText, Trash2, Download,
  Search, AlertTriangle, Target, ChevronDown, ChevronRight, ExternalLink,
  Brain, Crosshair, Shield, Edit3, Check, RotateCcw, Image, Paperclip,
  Share2, Network, Users, ClipboardList, Palette, ShieldAlert, BookOpen, Server, Link2, Calendar, LayoutDashboard
} from 'lucide-react';

const SEV_COLORS = {
  critical: '#dc2626', high: '#f97316', medium: '#eab308',
  low: '#3b82f6', info: '#6b7280'
};

const RETEST_OPTIONS = [
  { value: '', label: 'No Status' },
  { value: 'open', label: 'Open' },
  { value: 'remediated', label: 'Remediated' },
  { value: 'retest_needed', label: 'Retest Needed' },
  { value: 'accepted_risk', label: 'Accepted Risk' },
];

const RETEST_COLORS = {
  open: 'bg-severity-high/15 text-severity-high border-severity-high/30',
  remediated: 'bg-green-500/15 text-green-500 border-green-500/30',
  retest_needed: 'bg-yellow-500/15 text-yellow-500 border-yellow-500/30',
  accepted_risk: 'bg-blue-500/15 text-blue-500 border-blue-500/30',
};

const EMPTY_FINDING_TEMPLATE_FORM = {
  name: '', category: '', title: '', description: '', severity: 'medium',
  cvss_score: '', remediation: '',
};

function formatFileSize(bytes) {
  if (bytes == null) return 'File unavailable';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function RetestBadge({ status }) {
  if (!status) return null;
  const label = RETEST_OPTIONS.find(o => o.value === status)?.label || status;
  return (
    <span className={`badge border ${RETEST_COLORS[status] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'}`}>
      {status === 'remediated' && <Check size={10} className="mr-1" />}
      {status === 'retest_needed' && <RotateCcw size={10} className="mr-1" />}
      {label}
    </span>
  );
}

// Severity chart
function SeverityChart({ findings }) {
  const counts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  findings.forEach(f => { counts[f.severity] = (counts[f.severity] || 0) + 1; });

  const pieData = Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name: name.charAt(0).toUpperCase() + name.slice(1), value, color: SEV_COLORS[name] }));

  const barData = Object.entries(counts).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    count: value,
    fill: SEV_COLORS[name],
  }));

  if (findings.length === 0) return null;

  return (
    <div className="card p-5 mb-6">
      <h3 className="text-sm font-semibold themed-text-primary mb-4">Severity Breakdown</h3>
      <div className="flex items-center gap-8">
        <div className="w-40 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={35} outerRadius={65}
                paddingAngle={2} strokeWidth={0}>
                {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-primary)' }}
                itemStyle={{ color: 'var(--text-primary)' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 min-w-0 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={65} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-primary)' }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {barData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-2 text-sm min-w-[100px]">
          <div className="font-mono themed-text-muted text-xs uppercase tracking-wider mb-2">Total: {findings.length}</div>
          {Object.entries(counts).filter(([,v]) => v > 0).map(([sev, count]) => (
            <div key={sev} className="flex items-center justify-between gap-3">
              <SeverityBadge severity={sev} />
              <span className="font-mono themed-text-primary">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Tab button
function Tab({ active, label, icon: Icon, count, onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
      style={{
        borderColor: active ? 'var(--accent-red)' : 'transparent',
        color: active ? 'var(--accent-red)' : 'var(--text-muted)',
      }}
    >
      <Icon size={16} />
      {label}
      {count > 0 && (
        <span className="text-xs font-mono px-1.5 py-0.5 rounded"
          style={{ backgroundColor: active ? 'rgba(239,68,68,0.15)' : 'var(--bg-600)' }}>
          {count}
        </span>
      )}
    </button>
  );
}

// Finding editor form (shared between Add and Edit)
function FindingForm({ form, setForm, onSubmit, saving, submitLabel, showRetest = true }) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label htmlFor="finding-title" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Title</label>
        <input id="finding-title" className="input-field text-sm" value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })} required autoFocus />
      </div>
      <div className={`grid ${showRetest ? 'grid-cols-3' : 'grid-cols-2'} gap-3`}>
        {showRetest && <div>
          <label htmlFor="finding-severity" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Severity</label>
          <select id="finding-severity" className="input-field text-sm" value={form.severity}
            onChange={(e) => setForm({ ...form, severity: e.target.value })}>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>
        </div>}
        <div>
          <label htmlFor="finding-cvss" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">CVSS Score</label>
          <input id="finding-cvss" type="number" step="0.1" min="0" max="10" className="input-field text-sm"
            value={form.cvss_score} onChange={(e) => setForm({ ...form, cvss_score: e.target.value })}
            placeholder="7.5" />
        </div>
        <div>
          <label htmlFor="finding-retest" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Retest Status</label>
          <select id="finding-retest" className="input-field text-sm" value={form.retest_status || ''}
            onChange={(e) => setForm({ ...form, retest_status: e.target.value || null })}>
            {RETEST_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>
      {showRetest && <div>
        <label htmlFor="finding-retest-due" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Retest Due Date</label>
        <input id="finding-retest-due" type="date" className="input-field text-sm" value={form.retest_due_date || ''}
          onChange={(e) => setForm({ ...form, retest_due_date: e.target.value || null })} />
      </div>}
      <div>
        <label htmlFor="finding-hosts" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Affected Hosts</label>
        <input id="finding-hosts" className="input-field text-sm" value={form.affected_hosts}
          onChange={(e) => setForm({ ...form, affected_hosts: e.target.value })}
          placeholder="10.10.10.5, 10.10.10.12" />
      </div>
      <div>
        <label htmlFor="finding-description" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Description</label>
        <textarea id="finding-description" className="input-field text-sm resize-none" rows={3} value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </div>
      <div>
        <label htmlFor="finding-evidence" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Evidence</label>
        <textarea id="finding-evidence" className="input-field text-sm font-mono resize-none" rows={3} value={form.evidence}
          onChange={(e) => setForm({ ...form, evidence: e.target.value })}
          placeholder="Paste scan output, screenshots, etc." />
      </div>
      <div>
        <label htmlFor="finding-remediation" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Remediation</label>
        <textarea id="finding-remediation" className="input-field text-sm resize-none" rows={2} value={form.remediation}
          onChange={(e) => setForm({ ...form, remediation: e.target.value })} />
      </div>
      <div className="flex justify-end gap-3 pt-2">
        <button type="submit" disabled={saving} className="btn-primary flex items-center gap-2">
          {saving && <Spinner className="w-4 h-4" />} {submitLabel}
        </button>
      </div>
    </form>
  );
}

// Findings tab
function FindingsTab({ engId, findingsList, setFindingsList, toast }) {
  const [showAdd, setShowAdd] = useState(false);
  const [editFinding, setEditFinding] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [bulkAction, setBulkAction] = useState('');
  const [form, setForm] = useState({
    title: '', description: '', severity: 'medium', cvss_score: '',
    affected_hosts: '', evidence: '', remediation: '', retest_status: null, retest_due_date: null
  });
  const [saving, setSaving] = useState(false);
  const [findingQuery, setFindingQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [retestFilter, setRetestFilter] = useState('all');
  const [findingTemplates, setFindingTemplates] = useState([]);
  const [showTemplateManager, setShowTemplateManager] = useState(false);
  const [templateForm, setTemplateForm] = useState(EMPTY_FINDING_TEMPLATE_FORM);
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [duplicateMatches, setDuplicateMatches] = useState([]);

  const loadFindingTemplates = useCallback(async () => {
    const templates = await findingTemplatesApi.list();
    setFindingTemplates(templates);
    return templates;
  }, []);

  useEffect(() => {
    loadFindingTemplates().catch(err => toast({
      message: `Finding templates could not be loaded: ${err.message}`,
      type: 'error',
    }));
  }, [loadFindingTemplates, toast]);

  useEffect(() => {
    if (!showAdd || form.title.trim().length < 2) {
      setDuplicateMatches([]);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      findingsApi.duplicateCheck(engId, form.title.trim(), form.affected_hosts)
        .then(result => { if (!cancelled) setDuplicateMatches(result.matches || []); })
        .catch(() => { if (!cancelled) setDuplicateMatches([]); });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [engId, showAdd, form.title, form.affected_hosts]);

  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const dueSoonDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7);
  const dueSoon = `${dueSoonDate.getFullYear()}-${String(dueSoonDate.getMonth() + 1).padStart(2, '0')}-${String(dueSoonDate.getDate()).padStart(2, '0')}`;
  const normalizedFindingQuery = findingQuery.trim().toLowerCase();
  const displayedFindings = findingsList.filter(finding => {
    if (severityFilter !== 'all' && finding.severity !== severityFilter) return false;
    if (retestFilter === 'overdue' && !(finding.retest_due_date && finding.retest_due_date < today && ['open', 'retest_needed'].includes(finding.retest_status))) return false;
    if (retestFilter === 'due_soon' && !(finding.retest_due_date && finding.retest_due_date >= today && finding.retest_due_date <= dueSoon && ['open', 'retest_needed'].includes(finding.retest_status))) return false;
    if (retestFilter === 'none' && finding.retest_status) return false;
    if (!['all', 'overdue', 'due_soon', 'none'].includes(retestFilter) && finding.retest_status !== retestFilter) return false;
    if (!normalizedFindingQuery) return true;
    return [
      finding.title,
      finding.description,
      finding.affected_hosts,
      finding.evidence,
      finding.remediation,
      JSON.stringify(finding.evidence_refs || []),
    ].some(value => String(value || '').toLowerCase().includes(normalizedFindingQuery));
  });
  const displayedIds = new Set(displayedFindings.map(finding => finding.id));
  const allDisplayedSelected = displayedFindings.length > 0 && displayedFindings.every(finding => selected.has(finding.id));
  const overdueCount = findingsList.filter(finding => (
    finding.retest_due_date && finding.retest_due_date < today && ['open', 'retest_needed'].includes(finding.retest_status)
  )).length;
  const dueSoonCount = findingsList.filter(finding => (
    finding.retest_due_date && finding.retest_due_date >= today && finding.retest_due_date <= dueSoon && ['open', 'retest_needed'].includes(finding.retest_status)
  )).length;

  const resetForm = () => setForm({
    title: '', description: '', severity: 'medium', cvss_score: '',
    affected_hosts: '', evidence: '', remediation: '', retest_status: null, retest_due_date: null
  });

  const applyFindingTemplate = (templateId) => {
    const template = findingTemplates.find(item => item.id === templateId);
    if (!template) return;
    setForm(previous => ({
      ...previous,
      title: template.title || '',
      description: template.description || '',
      severity: template.severity || 'info',
      cvss_score: template.cvss_score != null ? String(template.cvss_score) : '',
      remediation: template.remediation || '',
    }));
  };

  const openTemplateManager = (finding = null) => {
    setEditingTemplateId(null);
    setTemplateForm(finding ? {
      name: finding.title || '',
      category: '',
      title: finding.title || '',
      description: finding.description || '',
      severity: finding.severity || 'info',
      cvss_score: finding.cvss_score != null ? String(finding.cvss_score) : '',
      remediation: finding.remediation || '',
    } : EMPTY_FINDING_TEMPLATE_FORM);
    setShowTemplateManager(true);
  };

  const editTemplate = (template) => {
    setEditingTemplateId(template.id);
    setTemplateForm({
      name: template.name || '',
      category: template.category || '',
      title: template.title || '',
      description: template.description || '',
      severity: template.severity || 'info',
      cvss_score: template.cvss_score != null ? String(template.cvss_score) : '',
      remediation: template.remediation || '',
    });
  };

  const handleSaveTemplate = async (event) => {
    event.preventDefault();
    setSavingTemplate(true);
    const body = {
      ...templateForm,
      category: templateForm.category || null,
      cvss_score: templateForm.cvss_score === '' ? null : parseFloat(templateForm.cvss_score),
    };
    try {
      if (editingTemplateId) {
        await findingTemplatesApi.update(editingTemplateId, body);
        toast({ message: `Finding template "${body.name}" updated`, type: 'success' });
      } else {
        await findingTemplatesApi.create(body);
        toast({ message: `Finding template "${body.name}" created`, type: 'success' });
      }
      await loadFindingTemplates();
      setEditingTemplateId(null);
      setTemplateForm(EMPTY_FINDING_TEMPLATE_FORM);
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSavingTemplate(false);
    }
  };

  const openEdit = (finding) => {
    setForm({
      title: finding.title || '',
      description: finding.description || '',
      severity: finding.severity || 'medium',
      cvss_score: finding.cvss_score != null ? String(finding.cvss_score) : '',
      affected_hosts: finding.affected_hosts || '',
      evidence: finding.evidence || '',
      remediation: finding.remediation || '',
      retest_status: finding.retest_status || null,
      retest_due_date: finding.retest_due_date || null,
    });
    setEditFinding(finding);
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await findingsApi.create(engId, {
        ...form,
        cvss_score: form.cvss_score ? parseFloat(form.cvss_score) : null,
      });
      const ordered = await findingsApi.list(engId);
      setFindingsList(ordered);
      setShowAdd(false);
      resetForm();
      toast({ message: 'Finding added', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await findingsApi.update(engId, editFinding.id, {
        ...form,
        cvss_score: form.cvss_score ? parseFloat(form.cvss_score) : null,
      });
      setFindingsList(prev => prev.map(f => f.id === editFinding.id ? updated : f));
      setEditFinding(null);
      resetForm();
      toast({ message: 'Finding updated', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (findingId) => {
    const finding = findingsList.find(item => item.id === findingId);
    if (!window.confirm(`Delete finding "${finding?.title || 'Untitled'}" and its stored evidence? This cannot be undone without a backup.`)) return;
    try {
      await findingsApi.delete(engId, findingId);
      setFindingsList(prev => prev.filter(f => f.id !== findingId));
      toast({ message: 'Finding deleted', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  const toggleSelect = (id) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleAll = () => {
    setSelected(previous => {
      const next = new Set(previous);
      if (allDisplayedSelected) displayedIds.forEach(id => next.delete(id));
      else displayedIds.forEach(id => next.add(id));
      return next;
    });
  };
  const handleBulk = async (action, value) => {
    if (selected.size === 0) return;
    try {
      await findingsApi.bulk(engId, [...selected], action, value);
      if (action === 'delete') {
        setFindingsList(prev => prev.filter(f => !selected.has(f.id)));
        toast({ message: `Deleted ${selected.size} findings`, type: 'success' });
      } else {
        const updated = await findingsApi.list(engId);
        setFindingsList(updated);
        toast({ message: `Updated ${selected.size} findings`, type: 'success' });
      }
      setSelected(new Set());
    } catch (err) { toast({ message: err.message, type: 'error' }); }
  };

  return (
    <div>
      {findingsList.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No findings yet"
          description="Add findings manually or upload scan data and run AI analysis."
          action={
            <div className="flex gap-2">
              <button onClick={() => openTemplateManager()} className="btn-secondary flex items-center gap-2">
                <BookOpen size={16} /> Finding Templates
              </button>
              <button onClick={() => { resetForm(); setShowAdd(true); }} className="btn-primary flex items-center gap-2">
                <Plus size={16} /> Add Finding
              </button>
            </div>
          }
        />
      ) : (
        <>
          <div className="grid sm:grid-cols-[minmax(0,1fr)_10rem_12rem] gap-3 mb-4">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
              <input
                className="input w-full pl-9"
                value={findingQuery}
                onChange={event => setFindingQuery(event.target.value)}
                placeholder="Filter accepted findings"
                aria-label="Filter accepted findings"
              />
            </div>
            <select className="input" value={severityFilter} onChange={event => setSeverityFilter(event.target.value)} aria-label="Filter findings by severity">
              <option value="all">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Informational</option>
            </select>
            <select className="input" value={retestFilter} onChange={event => setRetestFilter(event.target.value)} aria-label="Filter findings by retest state">
              <option value="all">All retest states</option>
              <option value="overdue">Overdue ({overdueCount})</option>
              <option value="due_soon">Due in 7 days ({dueSoonCount})</option>
              <option value="retest_needed">Retest needed</option>
              <option value="open">Open</option>
              <option value="remediated">Remediated</option>
              <option value="accepted_risk">Accepted risk</option>
              <option value="none">No retest state</option>
            </select>
          </div>
          <div className="flex items-center justify-between mb-4">
            <div>
              {selected.size > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono themed-text-muted">{selected.size} selected</span>
                  <select className="input-field text-xs py-1" style={{ width: 140 }}
                    value="" onChange={(e) => {
                      const v = e.target.value;
                      if (v === 'delete') {
                        if (window.confirm(`Delete ${selected.size} findings?`)) handleBulk('delete');
                      } else if (v.startsWith('sev:')) handleBulk('update_severity', v.slice(4));
                      else if (v.startsWith('ret:')) handleBulk('update_retest', v.slice(4));
                      e.target.value = '';
                    }}>
                    <option value="">Bulk Action...</option>
                    <option value="delete">Delete Selected</option>
                    <optgroup label="Set Severity">
                      <option value="sev:critical">Critical</option>
                      <option value="sev:high">High</option>
                      <option value="sev:medium">Medium</option>
                      <option value="sev:low">Low</option>
                      <option value="sev:info">Info</option>
                    </optgroup>
                    <optgroup label="Set Retest Status">
                      <option value="ret:open">Open</option>
                      <option value="ret:remediated">Remediated</option>
                      <option value="ret:retest_needed">Retest Needed</option>
                      <option value="ret:accepted_risk">Accepted Risk</option>
                    </optgroup>
                  </select>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={async () => {
                try {
                  await workflowApi.downloadFindingsCsv(engId, true);
                  toast({ message: 'Redacted findings CSV downloaded', type: 'success' });
                } catch (err) {
                  toast({ message: err.message, type: 'error' });
                }
              }} className="btn-secondary flex items-center gap-2 text-sm" title="Export a spreadsheet-safe CSV with common secrets redacted">
                <Download size={14} /> CSV
              </button>
              <button onClick={() => openTemplateManager()} className="btn-secondary flex items-center gap-2 text-sm">
                <BookOpen size={14} /> Templates
              </button>
              <button onClick={() => { resetForm(); setShowAdd(true); }} className="btn-secondary flex items-center gap-2 text-sm">
                <Plus size={14} /> Add Finding
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs font-mono themed-text-muted uppercase tracking-wider"
                  style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className="py-3 px-2 w-8">
                    <input type="checkbox" checked={allDisplayedSelected}
                      onChange={toggleAll} />
                  </th>
                  <th className="text-left py-3 px-4">Severity</th>
                  <th className="text-left py-3 px-4">Title</th>
                  <th className="text-left py-3 px-4">CVSS</th>
                  <th className="text-left py-3 px-4">Hosts</th>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-left py-3 px-4">Source</th>
                  <th className="py-3 px-4 w-20"></th>
                </tr>
              </thead>
              <tbody>
                {displayedFindings.map(f => (
                  <FindingRow key={f.id} finding={f} engId={engId}
                    selected={selected.has(f.id)}
                    onToggleSelect={() => toggleSelect(f.id)}
                    onEdit={() => openEdit(f)}
                    onSaveTemplate={() => openTemplateManager(f)}
                    onDelete={() => handleDelete(f.id)}
                    toast={toast} />
                ))}
              </tbody>
            </table>
          </div>
          {displayedFindings.length === 0 && (
            <div className="py-10 text-center text-sm themed-text-muted">No findings match the current filters.</div>
          )}
        </>
      )}

      {/* Add modal */}
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Finding" wide>
        {findingTemplates.length > 0 && (
          <div className="mb-4">
            <label htmlFor="finding-template-picker" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Start from a template</label>
            <select id="finding-template-picker" className="input-field text-sm" defaultValue=""
              onChange={event => applyFindingTemplate(event.target.value)}>
              <option value="">Blank finding</option>
              {findingTemplates.map(template => (
                <option key={template.id} value={template.id}>
                  {template.category ? `${template.category}: ` : ''}{template.name}
                </option>
              ))}
            </select>
            <p className="text-xs themed-text-muted mt-1">Templates fill reusable wording and scoring. Target-specific hosts and evidence stay blank.</p>
          </div>
        )}
        {duplicateMatches.length > 0 && (
          <div className="mb-4 rounded-md border border-yellow-500/40 bg-yellow-500/5 p-3" role="status">
            <div className="flex items-start gap-2">
              <AlertTriangle size={15} className="text-yellow-400 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-xs font-medium themed-text-primary">A finding with this title already exists.</p>
                <p className="text-[10px] themed-text-muted mt-0.5">Review the existing record before saving. You can still create a separate finding when the affected system or evidence differs.</p>
              </div>
            </div>
            <div className="space-y-1 mt-2">
              {duplicateMatches.slice(0, 3).map(match => (
                <div key={match.id} className="flex items-center gap-2 rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                  <SeverityBadge severity={match.severity} />
                  <span className="text-xs themed-text-secondary flex-1 truncate">{match.title}{match.affected_hosts ? ` · ${match.affected_hosts}` : ''}</span>
                  {match.host_overlap && <span className="text-[10px] text-yellow-300">Same host</span>}
                  <button type="button" className="btn-ghost text-xs" onClick={() => {
                    setFindingQuery(match.title);
                    setShowAdd(false);
                  }}>Review existing</button>
                </div>
              ))}
            </div>
          </div>
        )}
        <FindingForm form={form} setForm={setForm} onSubmit={handleAdd} saving={saving} submitLabel="Save Finding" />
      </Modal>

      {/* Edit modal */}
      <Modal open={!!editFinding} onClose={() => setEditFinding(null)} title="Edit Finding" wide>
        <FindingForm form={form} setForm={setForm} onSubmit={handleEdit} saving={saving} submitLabel="Update Finding" />
      </Modal>

      <Modal open={showTemplateManager} onClose={() => setShowTemplateManager(false)} title="Finding Templates" wide>
        <div className="space-y-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm themed-text-muted">Reuse finding language without carrying target-specific hosts or evidence into another assessment.</p>
            <label className="btn-secondary flex items-center gap-2 text-sm cursor-pointer shrink-0">
              <Upload size={14} /> Import
              <input type="file" accept=".json" className="hidden" onChange={async event => {
                const file = event.target.files[0];
                if (!file) return;
                try {
                  const imported = await findingTemplatesApi.import(file);
                  await loadFindingTemplates();
                  toast({ message: `Imported finding template "${imported.name}"`, type: 'success' });
                } catch (err) {
                  toast({ message: err.message, type: 'error' });
                }
                event.target.value = '';
              }} />
            </label>
          </div>
          {findingTemplates.length > 0 && (
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {findingTemplates.map(template => (
                <div key={template.id} className="rounded border p-3 flex items-start gap-3" style={{ borderColor: 'var(--border)' }}>
                  <SeverityBadge severity={template.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm themed-text-primary">{template.name}</div>
                    <div className="text-xs themed-text-muted mt-1">{[template.category, template.title, template.cvss_score != null && `CVSS ${template.cvss_score}`].filter(Boolean).join(' · ')}</div>
                  </div>
                  <button className="btn-ghost p-1" title="Edit template" onClick={() => editTemplate(template)}><Edit3 size={14} /></button>
                  <button className="btn-ghost p-1" title="Export template" onClick={async () => {
                    try { await findingTemplatesApi.export(template.id); }
                    catch (err) { toast({ message: err.message, type: 'error' }); }
                  }}><Download size={14} /></button>
                  <button className="btn-ghost p-1 text-red-400" title="Delete template" onClick={async () => {
                    if (!window.confirm(`Delete finding template "${template.name}"?`)) return;
                    try {
                      await findingTemplatesApi.delete(template.id);
                      setFindingTemplates(previous => previous.filter(item => item.id !== template.id));
                      if (editingTemplateId === template.id) {
                        setEditingTemplateId(null);
                        setTemplateForm(EMPTY_FINDING_TEMPLATE_FORM);
                      }
                      toast({ message: `Finding template "${template.name}" deleted`, type: 'success' });
                    } catch (err) { toast({ message: err.message, type: 'error' }); }
                  }}><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          )}
          <form onSubmit={handleSaveTemplate} className="card p-4 space-y-3">
            <h3 className="text-sm font-semibold themed-text-primary">{editingTemplateId ? 'Edit template' : 'New template'}</h3>
            <div className="grid sm:grid-cols-2 gap-3">
              <input className="input-field text-sm" value={templateForm.name}
                onChange={event => setTemplateForm(previous => ({ ...previous, name: event.target.value }))}
                placeholder="Template name" aria-label="Finding template name" required />
              <input className="input-field text-sm" value={templateForm.category}
                onChange={event => setTemplateForm(previous => ({ ...previous, category: event.target.value }))}
                placeholder="Category, such as Network" aria-label="Finding template category" />
            </div>
            <input className="input-field text-sm" value={templateForm.title}
              onChange={event => setTemplateForm(previous => ({ ...previous, title: event.target.value }))}
              placeholder="Finding title" aria-label="Finding template title" required />
            <div className="grid grid-cols-2 gap-3">
              <select className="input-field text-sm" value={templateForm.severity}
                onChange={event => setTemplateForm(previous => ({ ...previous, severity: event.target.value }))}
                aria-label="Finding template severity">
                {['critical', 'high', 'medium', 'low', 'info'].map(severity => <option key={severity} value={severity}>{severity[0].toUpperCase() + severity.slice(1)}</option>)}
              </select>
              <input type="number" min="0" max="10" step="0.1" className="input-field text-sm" value={templateForm.cvss_score}
                onChange={event => setTemplateForm(previous => ({ ...previous, cvss_score: event.target.value }))}
                placeholder="CVSS score" aria-label="Finding template CVSS score" />
            </div>
            <textarea className="input-field text-sm resize-none" rows={3} value={templateForm.description}
              onChange={event => setTemplateForm(previous => ({ ...previous, description: event.target.value }))}
              placeholder="Reusable description" aria-label="Finding template description" />
            <textarea className="input-field text-sm resize-none" rows={3} value={templateForm.remediation}
              onChange={event => setTemplateForm(previous => ({ ...previous, remediation: event.target.value }))}
              placeholder="Reusable remediation" aria-label="Finding template remediation" />
            <div className="flex justify-end gap-2">
              {editingTemplateId && <button type="button" className="btn-secondary text-sm" onClick={() => {
                setEditingTemplateId(null);
                setTemplateForm(EMPTY_FINDING_TEMPLATE_FORM);
              }}>Cancel edit</button>}
              <button type="submit" className="btn-primary text-sm" disabled={savingTemplate}>
                {savingTemplate ? 'Saving...' : editingTemplateId ? 'Update Template' : 'Create Template'}
              </button>
            </div>
          </form>
        </div>
      </Modal>
    </div>
  );
}

// Finding row with evidence support
function FindingRow({ finding, engId, selected, onToggleSelect, onEdit, onSaveTemplate, onDelete, toast }) {
  const [expanded, setExpanded] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const evidenceUrls = useRef(new Set());

  useEffect(() => () => {
    evidenceUrls.current.forEach(url => URL.revokeObjectURL(url));
    evidenceUrls.current.clear();
  }, []);

  const withObjectUrl = async (attachment) => {
    const objectUrl = await evidenceApi.objectUrl(attachment.url);
    evidenceUrls.current.add(objectUrl);
    return { ...attachment, objectUrl };
  };

  const loadEvidence = async () => {
    if (attachments.length > 0) return;
    setLoadingEvidence(true);
    try {
      const data = await evidenceApi.list(engId, finding.id);
      const hydrated = await Promise.all(data.map(async (attachment) => {
        try {
          return await withObjectUrl(attachment);
        } catch {
          return { ...attachment, objectUrl: null, loadError: true };
        }
      }));
      setAttachments(hydrated);
      const unavailable = hydrated.filter(attachment => attachment.loadError).length;
      if (unavailable > 0) {
        toast({
          message: `${unavailable} evidence file${unavailable === 1 ? ' is' : 's are'} unavailable. The record can still be removed.`,
          type: 'error',
        });
      }
    } catch (e) {
      toast({ message: `Could not load evidence: ${e.message}`, type: 'error' });
    }
    finally { setLoadingEvidence(false); }
  };

  const handleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      loadEvidence();
      if (history.length === 0) {
        setLoadingHistory(true);
        findingsApi.history(engId, finding.id)
          .then(setHistory)
          .catch((e) => toast({ message: `Could not load finding history: ${e.message}`, type: 'error' }))
          .finally(() => setLoadingHistory(false));
      }
    }
  };

  const handleUploadEvidence = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const att = await evidenceApi.upload(engId, finding.id, file);
      setAttachments(prev => [att, ...prev]);
      const hydrated = await withObjectUrl(att);
      setAttachments(prev => prev.map(item => item.id === att.id ? hydrated : item));
      toast({ message: `Attached ${att.filename}`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
    e.target.value = '';
  };

  const handleDeleteEvidence = async (attId) => {
    const attachment = attachments.find(item => item.id === attId);
    if (!window.confirm(`Delete evidence attachment "${attachment?.filename || 'Untitled'}"? This removes the stored file.`)) return;
    try {
      await evidenceApi.delete(engId, finding.id, attId);
      const removed = attachments.find(a => a.id === attId);
      if (removed?.objectUrl) {
        URL.revokeObjectURL(removed.objectUrl);
        evidenceUrls.current.delete(removed.objectUrl);
      }
      setAttachments(prev => prev.filter(a => a.id !== attId));
      toast({ message: 'Attachment deleted', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  return (
    <>
      <tr className="cursor-pointer transition-colors"
        style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}
        onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
        onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
        onClick={() => handleExpand()}>
        <td className="py-3 px-2 w-8" onClick={e => e.stopPropagation()}>
          <input type="checkbox" checked={selected || false} onChange={onToggleSelect} />
        </td>
        <td className="py-3 px-4"><SeverityBadge severity={finding.severity} /></td>
        <td className="py-3 px-4 themed-text-primary font-medium">
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown size={14} className="themed-text-muted shrink-0" /> :
              <ChevronRight size={14} className="themed-text-muted shrink-0" />}
            {finding.title}
          </div>
        </td>
        <td className="py-3 px-4 font-mono themed-text-secondary">{finding.cvss_score ?? '-'}</td>
        <td className="py-3 px-4 themed-text-secondary text-xs font-mono truncate max-w-[200px]">
          {finding.affected_hosts || '-'}
        </td>
        <td className="py-3 px-4">
          <RetestBadge status={finding.retest_status} />
          {finding.retest_due_date && <div className="text-[10px] font-mono themed-text-muted mt-1">Due {finding.retest_due_date}</div>}
        </td>
        <td className="py-3 px-4">
          <span className={`text-xs font-mono ${finding.ai_inference ? 'text-cyan-400' : 'themed-text-muted'}`}>
            {finding.ai_inference
              ? `AI reviewed${finding.ai_confidence != null ? ` ${Math.round(finding.ai_confidence * 100)}%` : ''}`
              : finding.source === 'imported'
              ? 'Imported'
              : finding.source === 'scan_reviewed'
              ? 'Scan reviewed'
              : finding.source === 'notebook_reviewed'
              ? 'Notebook reviewed'
              : 'Manual'}
          </span>
        </td>
        <td className="py-3 px-4">
          <div className="flex items-center gap-1">
            <button onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="themed-text-muted hover:text-blue-400 transition-colors p-1" title="Edit">
              <Edit3 size={14} />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onSaveTemplate(); }}
              className="themed-text-muted hover:text-cyan-400 transition-colors p-1" title="Save as template">
              <BookOpen size={14} />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="themed-text-muted hover:text-red-400 transition-colors p-1" title="Delete">
              <Trash2 size={14} />
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr style={{ backgroundColor: 'color-mix(in srgb, var(--bg-700) 30%, transparent)' }}>
          <td colSpan={8} className="px-4 py-4">
            <div className="grid grid-cols-1 gap-4 text-sm max-w-3xl ml-8">
              {finding.description && (
                <div>
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-1">Description</span>
                  <p className="themed-text-secondary whitespace-pre-wrap">{finding.description}</p>
                </div>
              )}
              {finding.evidence && (
                <div>
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-1">Evidence</span>
                  <pre className="themed-text-secondary font-mono text-xs rounded p-3 overflow-x-auto whitespace-pre-wrap"
                    style={{ backgroundColor: 'var(--bg-800)' }}>
                    {finding.evidence}
                  </pre>
                </div>
              )}
              {finding.evidence_refs?.length > 0 && (
                <div>
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-2">Evidence Provenance</span>
                  <div className="space-y-2">
                    {finding.evidence_refs.map(ref => (
                      <div key={ref.id} className="text-xs rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                        <div className="flex flex-wrap gap-2 font-mono">
                          <span className="text-cyan-400">{ref.id}</span>
                          <span className="themed-text-muted">{ref.filename || ref.scan_type || ref.tool}</span>
                          {ref.host && <span className="themed-text-secondary">{ref.host}{ref.port != null ? `:${ref.port}` : ''}</span>}
                          {ref.cve && <span className="themed-text-secondary">{ref.cve}</span>}
                          {ref.plugin_id && <span className="themed-text-secondary">Plugin {ref.plugin_id}</span>}
                        </div>
                        {ref.excerpt && <p className="themed-text-muted mt-1 whitespace-pre-wrap break-words">{ref.excerpt}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {finding.remediation && (
                <div>
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-1">Remediation</span>
                  <p className="themed-text-secondary whitespace-pre-wrap">{finding.remediation}</p>
                </div>
              )}
              <div>
                <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-2">Change History</span>
                {loadingHistory && <Spinner className="w-4 h-4 themed-text-muted" />}
                {!loadingHistory && history.length === 0 && <p className="text-xs themed-text-muted italic">No recorded changes.</p>}
                {history.length > 0 && <div className="space-y-2">
                  {history.map(entry => (
                    <div key={entry.id} className="text-xs rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                      <span className="themed-text-primary font-medium">{entry.action.replaceAll('_', ' ')}</span>
                      <span className="themed-text-muted ml-2">{entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}</span>
                      <div className="themed-text-muted mt-1">{Object.keys(entry.changes || {}).join(', ')}</div>
                    </div>
                  ))}
                </div>}
              </div>
              {/* Evidence Attachments */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider flex items-center gap-1.5">
                    <Paperclip size={12} /> Evidence Attachments
                    {attachments.length > 0 && ` (${attachments.length})`}
                  </span>
                  <label className="btn-ghost flex items-center gap-1 text-xs cursor-pointer">
                    <Image size={12} /> Attach
                    <input type="file" className="hidden" accept="image/*,.pdf,.txt,.http,.req,.resp,.md,.csv,.json,.har" onChange={handleUploadEvidence} />
                  </label>
                </div>
                {loadingEvidence && <Spinner className="w-4 h-4 themed-text-muted" />}
                {attachments.length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {attachments.map(att => (
                      <div key={att.id} className="relative group rounded overflow-hidden"
                        style={{ backgroundColor: 'var(--bg-800)', border: '1px solid var(--border)' }}>
                        {att.objectUrl && att.content_type?.startsWith('image/') ? (
                          <a href={att.objectUrl} target="_blank" rel="noopener noreferrer">
                            <img src={att.objectUrl} alt={att.filename}
                              className="w-full h-32 object-cover cursor-pointer hover:opacity-80 transition-opacity" />
                          </a>
                        ) : att.objectUrl ? (
                          <a href={att.objectUrl} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-2 p-3 text-xs themed-text-secondary hover:themed-text-primary">
                            <FileText size={14} /> {att.filename}
                          </a>
                        ) : (
                          <div className="flex items-center gap-2 p-3 text-xs text-red-400">
                            <FileText size={14} /> File unavailable
                          </div>
                        )}
                        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={(e) => { e.stopPropagation(); e.preventDefault(); handleDeleteEvidence(att.id); }}
                            className="p-1 rounded bg-black/60 text-white hover:bg-red-600 transition-colors">
                            <Trash2 size={12} />
                          </button>
                        </div>
                        <div className="px-2 py-1 text-xs themed-text-muted truncate">{att.filename}</div>
                      </div>
                    ))}
                  </div>
                )}
                {attachments.length === 0 && !loadingEvidence && (
                  <p className="text-xs themed-text-muted italic">No attachments. Click "Attach" to add screenshots or files.</p>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function AIDraftWorkbench({ engId, drafts, setDrafts, toast, onFindingsChanged }) {
  const [selected, setSelected] = useState(new Set());
  const [reviewing, setReviewing] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(null);

  useEffect(() => {
    setSelected(prev => new Set([...prev].filter(id => drafts.some(d => d.id === id))));
  }, [drafts]);

  const beginEdit = (draft) => {
    setEditing(draft);
    setForm({
      title: draft.title || '',
      description: draft.description || '',
      severity: draft.severity || 'info',
      cvss_score: draft.cvss_score != null ? String(draft.cvss_score) : '',
      affected_hosts: draft.affected_hosts || '',
      evidence: draft.evidence || '',
      remediation: draft.remediation || '',
      retest_status: null,
    });
  };

  const accept = async (draftId, edits = null) => {
    setReviewing(true);
    try {
      await analysisApi.acceptDraft(engId, draftId, edits);
      setDrafts(prev => prev.filter(draft => draft.id !== draftId));
      setEditing(null);
      await onFindingsChanged();
      toast({ message: 'AI proposal accepted and saved as a reviewed finding', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setReviewing(false);
    }
  };

  const reject = async (draftId) => {
    setReviewing(true);
    try {
      await analysisApi.rejectDraft(engId, draftId);
      setDrafts(prev => prev.filter(draft => draft.id !== draftId));
      toast({ message: 'AI proposal rejected', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setReviewing(false);
    }
  };

  const reviewSelected = async (action) => {
    if (selected.size === 0) return;
    setReviewing(true);
    try {
      await analysisApi.reviewDrafts(engId, [...selected], action);
      setDrafts(prev => prev.filter(draft => !selected.has(draft.id)));
      if (action === 'accept') await onFindingsChanged();
      toast({
        message: `${selected.size} AI proposal${selected.size === 1 ? '' : 's'} ${action === 'accept' ? 'accepted' : 'rejected'}`,
        type: 'success',
      });
      setSelected(new Set());
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setReviewing(false);
    }
  };

  if (drafts.length === 0) return null;

  return (
    <div className="card p-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Shield size={16} className="text-cyan-400" />
            <h3 className="text-sm font-semibold themed-text-primary">AI Review Workbench</h3>
            <span className="badge border bg-cyan-500/15 text-cyan-400 border-cyan-500/30">
              {drafts.length} pending
            </span>
          </div>
          <p className="text-xs themed-text-muted">
            Nothing is added to Findings until you accept it. Evidence IDs link each proposal to scanner observations.
          </p>
        </div>
        <div className="flex gap-2">
          <button disabled={reviewing || selected.size === 0} onClick={() => reviewSelected('reject')}
            className="btn-ghost text-sm text-red-400">Reject selected</button>
          <button disabled={reviewing || selected.size === 0} onClick={() => reviewSelected('accept')}
            className="btn-primary text-sm">Accept selected</button>
        </div>
      </div>

      <div className="space-y-3">
        {drafts.map(draft => {
          const confidence = draft.confidence == null ? null : Math.round(draft.confidence * 100);
          const current = draft.target_finding;
          const changedFields = current ? [
            ['Title', current.title, draft.title],
            ['Severity', current.severity, draft.severity],
            ['CVSS', current.cvss_score ?? 'Not scored', draft.cvss_score ?? 'Not scored'],
            ['Hosts', current.affected_hosts || 'Not specified', draft.affected_hosts || 'Not specified'],
          ].filter(([, before, after]) => String(before) !== String(after)) : [];
          return (
            <div key={draft.id} className="rounded border p-4" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-700)' }}>
              <div className="flex items-start gap-3">
                <input type="checkbox" className="mt-1" checked={selected.has(draft.id)}
                  aria-label={`Select ${draft.title}`}
                  onChange={() => setSelected(prev => {
                    const next = new Set(prev);
                    if (next.has(draft.id)) next.delete(draft.id); else next.add(draft.id);
                    return next;
                  })} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={draft.severity} />
                    <h4 className="font-medium themed-text-primary">{draft.title}</h4>
                    <span className="badge" style={{ backgroundColor: 'var(--bg-600)', color: 'var(--text-muted)' }}>
                      {draft.operation === 'update' ? 'Proposed update' : 'New proposal'}
                    </span>
                    {confidence != null && (
                      <span className="text-xs font-mono themed-text-muted">Evidence confidence: {confidence}%</span>
                    )}
                  </div>
                  <p className="text-sm themed-text-secondary mt-2 whitespace-pre-wrap">{draft.description || 'No description provided.'}</p>
                  <div className="grid sm:grid-cols-2 gap-3 mt-3 text-xs">
                    <div><span className="themed-text-muted">Hosts:</span> <span className="font-mono themed-text-secondary">{draft.affected_hosts || 'Not specified'}</span></div>
                    <div><span className="themed-text-muted">CVSS:</span> <span className="font-mono themed-text-secondary">{draft.cvss_score ?? 'Not scored'}</span></div>
                  </div>

                  {changedFields.length > 0 && (
                    <div className="mt-3 p-3 rounded" style={{ backgroundColor: 'var(--bg-800)' }}>
                      <div className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-2">Create versus update diff</div>
                      {changedFields.map(([label, before, after]) => (
                        <div key={label} className="text-xs grid grid-cols-[80px_1fr_20px_1fr] gap-2 py-1">
                          <span className="themed-text-muted">{label}</span>
                          <span className="text-red-300 break-words">{String(before)}</span>
                          <span className="themed-text-muted">to</span>
                          <span className="text-green-300 break-words">{String(after)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-3">
                    <div className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-2">Evidence provenance</div>
                    <div className="space-y-2">
                      {(draft.evidence_refs || []).map(ref => (
                        <div key={ref.id} className="text-xs rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                          <div className="flex flex-wrap gap-2 font-mono">
                            <span className="text-cyan-400">{ref.id}</span>
                            <span className="themed-text-muted">{ref.filename || ref.scan_type || ref.tool}</span>
                            {ref.host && <span className="themed-text-secondary">{ref.host}{ref.port != null ? `:${ref.port}` : ''}</span>}
                            {ref.cve && <span className="themed-text-secondary">{ref.cve}</span>}
                            {ref.plugin_id && <span className="themed-text-secondary">Plugin {ref.plugin_id}</span>}
                          </div>
                          {ref.excerpt && <p className="themed-text-muted mt-1 whitespace-pre-wrap break-words">{ref.excerpt}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col gap-2 shrink-0">
                  <button disabled={reviewing} onClick={() => accept(draft.id)} className="btn-primary text-xs flex items-center gap-1">
                    <Check size={13} /> Accept
                  </button>
                  <button disabled={reviewing} onClick={() => beginEdit(draft)} className="btn-secondary text-xs flex items-center gap-1">
                    <Edit3 size={13} /> Edit
                  </button>
                  <button disabled={reviewing} onClick={() => reject(draft.id)} className="btn-ghost text-xs text-red-400">
                    Reject
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Modal open={!!editing} onClose={() => setEditing(null)} title="Edit and accept AI proposal" wide>
        {form && <FindingForm
          form={form}
          setForm={setForm}
          saving={reviewing}
          submitLabel="Accept reviewed finding"
          showRetest={false}
          onSubmit={(event) => {
            event.preventDefault();
            const { retest_status, ...edits } = form;
            accept(editing.id, {
              ...edits,
              cvss_score: edits.cvss_score ? parseFloat(edits.cvss_score) : null,
            });
          }}
        />}
      </Modal>
    </div>
  );
}

const ASSET_STATUS_STYLES = {
  regressed: 'bg-severity-critical/15 text-severity-critical border-severity-critical/30',
  new: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  persistent: 'bg-yellow-500/15 text-yellow-500 border-yellow-500/30',
};

function RetestsTab({ engId, toast, onFindingsChanged, onOpenFindings }) {
  const [overview, setOverview] = useState(null);
  const [loadingRetests, setLoadingRetests] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);

  const loadOverview = useCallback(async () => {
    const data = await workflowApi.retestOverview(engId);
    setOverview(data);
    return data;
  }, [engId]);

  useEffect(() => {
    loadOverview()
      .catch(err => toast({ message: `Retest work view could not be loaded: ${err.message}`, type: 'error' }))
      .finally(() => setLoadingRetests(false));
  }, [loadOverview, toast]);

  const changeStatus = async (finding, status) => {
    setUpdatingId(finding.id);
    try {
      await findingsApi.update(engId, finding.id, { retest_status: status });
      await Promise.all([loadOverview(), onFindingsChanged()]);
      toast({ message: `${finding.title} marked ${status.replace('_', ' ')}`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setUpdatingId(null);
    }
  };

  if (loadingRetests) return <div className="flex justify-center py-16"><Spinner className="w-6 h-6 themed-text-muted" /></div>;
  if (!overview) return null;
  const sections = [
    ['overdue', 'Overdue', 'Past the recorded due date', 'text-red-400'],
    ['due_soon', 'Due in 7 days', 'Scheduled for the next seven days', 'text-yellow-400'],
    ['unscheduled', 'Needs scheduling', 'Open retests without a due date', 'text-blue-400'],
    ['scheduled', 'Scheduled later', 'Due beyond the next seven days', 'themed-text-secondary'],
    ['recently_resolved', 'Recently remediated', 'Closed during the last 30 days', 'text-green-400'],
  ];
  const activeCount = overview.summary.overdue + overview.summary.due_soon + overview.summary.unscheduled + overview.summary.scheduled;

  return (
    <div>
      <SectionHeader title="Retest Work" description={`Local work view as of ${overview.as_of}`} action={<button className="btn-secondary text-sm" onClick={onOpenFindings}>Open Findings</button>} />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
        {sections.map(([key, label]) => (
          <div key={key} className="card p-4">
            <div className="text-2xl font-mono themed-text-primary">{overview.summary[key]}</div>
            <div className="text-xs themed-text-muted mt-1">{label}</div>
          </div>
        ))}
      </div>
      {activeCount === 0 && overview.summary.recently_resolved === 0 ? (
        <EmptyState icon={RotateCcw} title="No retest work" description="Add an open or retest-needed status to a finding to track it here." />
      ) : (
        <div className="space-y-4">
          {sections.filter(([key]) => overview[key].length > 0).map(([key, label, description, color]) => (
            <div key={key} className="card overflow-hidden">
              <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: 'var(--border)' }}>
                <Calendar size={15} className={color} />
                <div className="flex-1">
                  <h3 className={`text-sm font-semibold ${color}`}>{label}</h3>
                  <p className="text-xs themed-text-muted">{description}</p>
                </div>
                <span className="font-mono text-sm themed-text-secondary">{overview[key].length}</span>
              </div>
              <div>
                {overview[key].map(finding => (
                  <div key={finding.id} className="px-4 py-3 border-b last:border-b-0 flex flex-col sm:flex-row sm:items-center gap-3" style={{ borderColor: 'var(--border)' }}>
                    <SeverityBadge severity={finding.severity} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm themed-text-primary">{finding.title}</div>
                      <div className="text-xs themed-text-muted mt-1">
                        {[finding.affected_hosts, finding.retest_due_date && `due ${finding.retest_due_date}`, finding.retest_status.replace('_', ' ')].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                    {key === 'recently_resolved' ? (
                      <button className="btn-secondary text-xs" disabled={updatingId === finding.id} onClick={() => changeStatus(finding, 'retest_needed')}>Reopen</button>
                    ) : (
                      <button className="btn-secondary text-xs" disabled={updatingId === finding.id} onClick={() => changeStatus(finding, 'remediated')}>Mark remediated</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {overview.summary.accepted_risk > 0 && <p className="text-xs themed-text-muted mt-4">{overview.summary.accepted_risk} accepted-risk finding{overview.summary.accepted_risk === 1 ? '' : 's'} remain visible in Findings but are not active retest work.</p>}
    </div>
  );
}

function WorkspaceSearch({ engId, onOpenTab, toast }) {
  const [query, setQuery] = useState('');
  const [searchState, setSearchState] = useState({ loading: false, data: null });
  const requestSequence = useRef(0);
  const searchInput = useRef(null);

  useEffect(() => {
    const focusSearch = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchInput.current?.focus();
        searchInput.current?.select();
      }
    };
    document.addEventListener('keydown', focusSearch);
    return () => document.removeEventListener('keydown', focusSearch);
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    const sequence = ++requestSequence.current;
    if (trimmed.length < 2) {
      setSearchState({ loading: false, data: null });
      return undefined;
    }
    setSearchState(previous => ({ ...previous, loading: true }));
    const timer = setTimeout(() => {
      workflowApi.search(engId, trimmed, 50)
        .then(data => {
          if (requestSequence.current === sequence) setSearchState({ loading: false, data });
        })
        .catch(err => {
          if (requestSequence.current !== sequence) return;
          setSearchState({ loading: false, data: null });
          toast({ message: `Workspace search failed: ${err.message}`, type: 'error' });
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [engId, query, toast]);

  const results = searchState.data?.results || [];
  return (
    <div className="relative mb-5 z-20">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
        <input
          ref={searchInput}
          className="input w-full pl-10 pr-20"
          value={query}
          onChange={event => setQuery(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Escape') setQuery('');
            if (event.key === 'Enter' && results[0]) {
              onOpenTab(results[0].tab);
              setQuery('');
            }
          }}
          placeholder="Search this engagement: findings, assets, evidence, checklists, and exploitation chains"
          aria-label="Search this engagement"
        />
        {searchState.loading && <Spinner className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 themed-text-muted" />}
        {!searchState.loading && <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-mono themed-text-muted border rounded px-1.5 py-0.5">Ctrl K</kbd>}
      </div>
      {query.trim().length >= 2 && !searchState.loading && searchState.data && (
        <div className="absolute top-full left-0 right-0 mt-1 card shadow-xl max-h-[28rem] overflow-y-auto">
          <div className="px-3 py-2 border-b text-xs themed-text-muted" style={{ borderColor: 'var(--border)' }}>
            {searchState.data.count} local result{searchState.data.count === 1 ? '' : 's'}
            {searchState.data.limited ? ' · Refine your search to see more' : ''}
          </div>
          {results.map((result, index) => (
            <button
              key={`${result.type}-${result.id}-${index}`}
              className="w-full text-left px-4 py-3 border-b hover:bg-white/[0.03] last:border-b-0"
              style={{ borderColor: 'var(--border)' }}
              onClick={() => {
                onOpenTab(result.tab);
                setQuery('');
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm themed-text-primary truncate">{result.title}</div>
                  <div className="text-xs themed-text-muted mt-0.5">{result.subtitle}</div>
                </div>
                <span className="badge border themed-text-muted shrink-0">{result.type}</span>
              </div>
              {result.snippet && <p className="text-xs themed-text-secondary mt-2 line-clamp-2">{result.snippet}</p>}
            </button>
          ))}
          {results.length === 0 && <div className="px-4 py-8 text-sm text-center themed-text-muted">No matching workspace records.</div>}
        </div>
      )}
    </div>
  );
}

function AssetStatusBadge({ status }) {
  return (
    <span className={`badge border ${ASSET_STATUS_STYLES[status] || 'themed-text-muted'}`}>
      {status}
    </span>
  );
}

function AssetsTab({ engId, toast, onOpenScans, onOpenFindings, onFindingsChanged }) {
  const [inventory, setInventory] = useState(null);
  const [loadingAssets, setLoadingAssets] = useState(true);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [expanded, setExpanded] = useState(new Set());
  const [promoting, setPromoting] = useState(new Set());

  const loadInventory = useCallback(async () => {
    const data = await workflowApi.assets(engId);
    setInventory(data);
    return data;
  }, [engId]);

  useEffect(() => {
    let cancelled = false;
    setLoadingAssets(true);
    loadInventory()
      .then(data => { if (!cancelled) setInventory(data); })
      .catch(err => { if (!cancelled) toast({ message: `Asset inventory could not be loaded: ${err.message}`, type: 'error' }); })
      .finally(() => { if (!cancelled) setLoadingAssets(false); });
    return () => { cancelled = true; };
  }, [loadInventory, toast]);

  const acceptObservation = async (observation) => {
    setPromoting(previous => new Set([...previous, observation.fingerprint]));
    try {
      const finding = await workflowApi.acceptObservation(engId, inventory.snapshot.id, observation.fingerprint);
      await Promise.all([loadInventory(), onFindingsChanged()]);
      toast({ message: `Added ${finding.title} to Findings for review`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setPromoting(previous => {
        const next = new Set(previous);
        next.delete(observation.fingerprint);
        return next;
      });
    }
  };

  if (loadingAssets) {
    return <div className="flex justify-center py-16"><Spinner className="w-6 h-6 themed-text-muted" /></div>;
  }
  if (!inventory?.snapshot) {
    return (
      <EmptyState
        icon={Server}
        title="No versioned assets yet"
        description="Upload a supported scan and create a snapshot. Breachwright will build this inventory locally from the normalized results."
        action={<button className="btn-primary text-sm" onClick={onOpenScans}>Open Scans</button>}
      />
    );
  }

  const needle = query.trim().toLowerCase();
  const assets = inventory.assets.filter(asset => {
    if (statusFilter !== 'all' && asset.status !== statusFilter) return false;
    if (!needle) return true;
    return [
      asset.host,
      ...asset.display_hosts,
      ...(asset.aliases || []),
      ...(asset.operating_systems || []),
      ...asset.services.flatMap(item => [item.title, item.tool, item.evidence_ref?.service, item.evidence_ref?.product, item.evidence_ref?.version]),
      ...asset.vulnerabilities.flatMap(item => [item.title, item.tool, item.evidence_ref?.cve]),
      ...asset.findings.flatMap(item => [item.title, item.severity, item.retest_status]),
    ].some(value => String(value || '').toLowerCase().includes(needle));
  });
  const summaryCards = [
    ['Assets', inventory.summary.assets],
    ['Open services', inventory.summary.services],
    ['Scanner observations', inventory.summary.vulnerabilities],
    ['Linked findings', inventory.summary.linked_findings],
  ];

  return (
    <div>
      <SectionHeader
        title="Assets & Services"
        description={`Current view: ${inventory.snapshot.label}${inventory.baseline ? ` compared with ${inventory.baseline.label}` : ' (initial baseline)'}`}
        action={<button className="btn-secondary text-sm" onClick={onOpenScans}>Manage snapshots</button>}
      />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {summaryCards.map(([label, value]) => (
          <div key={label} className="card p-4">
            <div className="text-2xl font-mono font-semibold themed-text-primary">{value}</div>
            <div className="text-xs uppercase tracking-wider themed-text-muted mt-1">{label}</div>
          </div>
        ))}
      </div>
      {(inventory.summary.limited || inventory.summary.unlinked_findings > 0) && (
        <div className="card p-3 mb-4 text-sm themed-text-secondary flex items-start gap-2">
          <AlertTriangle size={16} className="text-yellow-500 mt-0.5 shrink-0" />
          <span>
            {inventory.summary.limited && `The inventory is displaying the first ${inventory.summary.asset_limit.toLocaleString()} normalized hosts. Summary counts remain complete. `}
            {inventory.summary.unlinked_findings > 0 && `${inventory.summary.unlinked_findings} finding(s) do not exactly match a scanned host and remain available in Findings.`}
          </span>
        </div>
      )}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            className="input w-full pl-9"
            placeholder="Search hosts, ports, products, CVEs, and findings"
            aria-label="Search asset inventory"
          />
        </div>
        <select value={statusFilter} onChange={event => setStatusFilter(event.target.value)} className="input sm:w-44" aria-label="Filter asset status">
          <option value="all">All change states</option>
          <option value="regressed">Regressed</option>
          <option value="new">New</option>
          <option value="persistent">Persistent</option>
        </select>
      </div>
      <div className="space-y-3">
        {assets.map(asset => {
          const isExpanded = expanded.has(asset.host);
          return (
            <div key={asset.host} className="card overflow-hidden">
              <button
                className="w-full p-4 flex items-center gap-3 text-left hover:bg-white/[0.02]"
                onClick={() => setExpanded(previous => {
                  const next = new Set(previous);
                  if (next.has(asset.host)) next.delete(asset.host); else next.add(asset.host);
                  return next;
                })}
                aria-expanded={isExpanded}
              >
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <Server size={17} className="themed-text-muted shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm themed-text-primary truncate">{asset.host}</div>
                  <div className="text-xs themed-text-muted mt-1">
                    Seen in {asset.snapshot_count} snapshot{asset.snapshot_count === 1 ? '' : 's'} · {asset.service_count} service{asset.service_count === 1 ? '' : 's'} · {asset.vulnerability_count} observation{asset.vulnerability_count === 1 ? '' : 's'}
                  </div>
                  {(asset.aliases?.length > 0 || asset.operating_systems?.length > 0) && (
                    <div className="text-xs themed-text-muted mt-1 truncate">
                      {[...(asset.aliases || []), ...(asset.operating_systems || [])].join(' · ')}
                    </div>
                  )}
                </div>
                <div className="hidden sm:flex items-center gap-2 shrink-0">
                  <SeverityBadge severity={asset.highest_severity} />
                  <AssetStatusBadge status={asset.status} />
                  {asset.finding_count > 0 && <span className="badge border themed-text-secondary"><Link2 size={10} className="mr-1" />{asset.finding_count}</span>}
                </div>
              </button>
              {isExpanded && (
                <div className="px-4 pb-4 border-t" style={{ borderColor: 'var(--border)' }}>
                  <div className="sm:hidden flex items-center gap-2 py-3">
                    <SeverityBadge severity={asset.highest_severity} />
                    <AssetStatusBadge status={asset.status} />
                  </div>
                  <div className="grid lg:grid-cols-2 gap-5 pt-4">
                    <div>
                      <h4 className="text-xs font-mono uppercase tracking-wider themed-text-muted mb-2">Open services</h4>
                      {asset.services.length === 0 && <p className="text-sm themed-text-muted">No service observations in this snapshot.</p>}
                      <div className="space-y-2">
                        {asset.services.map(service => (
                          <div key={service.fingerprint} className="rounded border p-3" style={{ borderColor: 'var(--border)' }}>
                            <div className="flex justify-between gap-2">
                              <span className="font-mono text-sm themed-text-primary">{service.port ?? '?'} / {service.evidence_ref?.protocol || 'unknown'}</span>
                              <AssetStatusBadge status={service.status} />
                            </div>
                            <div className="text-sm themed-text-secondary mt-1">
                              {[service.evidence_ref?.service, service.evidence_ref?.product, service.evidence_ref?.version].filter(Boolean).join(' · ') || service.title}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-xs font-mono uppercase tracking-wider themed-text-muted mb-2">Vulnerability observations</h4>
                      {asset.vulnerabilities.length === 0 && <p className="text-sm themed-text-muted">No vulnerability observations in this snapshot.</p>}
                      <div className="space-y-2">
                        {asset.vulnerabilities.map(observation => (
                          <div key={observation.fingerprint} className="rounded border p-3" style={{ borderColor: 'var(--border)' }}>
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-sm themed-text-primary">{observation.title}</span>
                              <SeverityBadge severity={observation.severity} />
                            </div>
                            <div className="text-xs themed-text-muted mt-1">
                              {[observation.evidence_ref?.cve, observation.port && `port ${observation.port}`, observation.tool].filter(Boolean).join(' · ')}
                            </div>
                            <div className="mt-2">
                              {observation.finding_id ? (
                                <button className="btn-ghost text-xs" onClick={onOpenFindings}><Link2 size={11} className="inline mr-1" />In Findings</button>
                              ) : (
                                <button
                                  className="btn-secondary text-xs"
                                  disabled={promoting.has(observation.fingerprint)}
                                  onClick={() => acceptObservation(observation)}
                                >
                                  {promoting.has(observation.fingerprint) ? 'Adding...' : 'Add to Findings'}
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  {asset.finding_count > 0 && (
                    <div className="mt-5">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-xs font-mono uppercase tracking-wider themed-text-muted">Linked findings</h4>
                        <button className="btn-ghost text-xs" onClick={onOpenFindings}>Open Findings</button>
                      </div>
                      <div className="grid lg:grid-cols-2 gap-2">
                        {asset.findings.map(finding => (
                          <div key={finding.id} className="rounded border p-3 flex items-start justify-between gap-3" style={{ borderColor: 'var(--border)' }}>
                            <div>
                              <div className="text-sm themed-text-primary">{finding.title}</div>
                              <div className="text-xs themed-text-muted mt-1">{finding.evidence_attachment_count} attachment{finding.evidence_attachment_count === 1 ? '' : 's'}{finding.retest_status ? ` · ${finding.retest_status.replace('_', ' ')}` : ''}</div>
                            </div>
                            <SeverityBadge severity={finding.severity} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {asset.details_limited && (
                    <p className="text-xs text-yellow-500 mt-4">
                      Detail rendering is limited to {inventory.summary.observation_limit_per_type} services and vulnerability observations of each type and {inventory.summary.finding_limit_per_asset} linked findings per asset. Summary counts remain complete.
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {assets.length === 0 && (
          <EmptyState icon={Search} title="No matching assets" description="Adjust the search text or change-state filter." />
        )}
      </div>
    </div>
  );
}

// Scans tab
function ScansTab({ engId, toast, onFindingsChanged }) {
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [scans, setScans] = useState([]);
  const [scanType, setScanType] = useState('auto');
  const [scanQuery, setScanQuery] = useState('');
  const [scanListType, setScanListType] = useState('all');
  const [loadingScans, setLoadingScans] = useState(true);
  const [analysisPreview, setAnalysisPreview] = useState(null);
  const [analysisScanIds, setAnalysisScanIds] = useState(new Set());
  const [drafts, setDrafts] = useState([]);
  const [snapshots, setSnapshots] = useState([]);
  const [selectedScanIds, setSelectedScanIds] = useState(new Set());
  const [snapshotLabel, setSnapshotLabel] = useState('');
  const [snapshotting, setSnapshotting] = useState(false);
  const [comparison, setComparison] = useState(null);
  const normalizedScanQuery = scanQuery.trim().toLowerCase();
  const visibleScans = scans.filter(scan => (
    (scanListType === 'all' || scan.scan_type === scanListType)
    && (!normalizedScanQuery || scan.filename.toLowerCase().includes(normalizedScanQuery))
  ));

  useEffect(() => {
    Promise.all([analysisApi.listScans(engId), workflowApi.listSnapshots(engId)])
      .then(([loadedScans, loadedSnapshots]) => {
        setScans(loadedScans);
        setSnapshots(loadedSnapshots);
        setAnalysisScanIds(new Set(loadedScans.slice(0, 50).map(scan => scan.id)));
        setSelectedScanIds(new Set());
      })
      .catch((err) => toast({ message: `Could not load scans: ${err.message}`, type: 'error' }))
      .finally(() => setLoadingScans(false));
  }, [engId, toast]);

  useEffect(() => {
    let cancelled = false;
    analysisApi.preview(engId, [...analysisScanIds])
      .then(preview => { if (!cancelled) setAnalysisPreview(preview); })
      .catch(err => { if (!cancelled) toast({ message: `AI input preflight failed: ${err.message}`, type: 'error' }); });
    return () => { cancelled = true; };
  }, [engId, analysisScanIds, toast]);

  useEffect(() => {
    analysisApi.listDrafts(engId)
      .then(setDrafts)
      .catch((err) => toast({ message: `Could not load AI review drafts: ${err.message}`, type: 'error' }));
  }, [engId, toast]);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const scan = await analysisApi.uploadScan(engId, file, scanType);
      setScans(prev => [...prev, scan]);
      setAnalysisScanIds(prev => prev.size < 50 ? new Set([...prev, scan.id]) : prev);
      if (scan.scan_type !== 'custom') {
        setSelectedScanIds(prev => new Set([...prev, scan.id]));
      }
      toast({
        message: `Uploaded ${scan.filename} as ${scan.scan_type}${scan.auto_detected ? ' (auto-detected)' : ''}`,
        type: 'success',
      });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const result = await analysisApi.run(engId, [...analysisScanIds]);
      const pending = await analysisApi.listDrafts(engId);
      setDrafts(pending);
      const discarded = result.summary?.unsupported_discarded || 0;
      toast({
        message: `Analysis prepared ${pending.length} review proposal${pending.length === 1 ? '' : 's'}${discarded ? ` and discarded ${discarded} ungrounded result${discarded === 1 ? '' : 's'}` : ''}`,
        type: 'success',
      });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setAnalyzing(false);
    }
  };

  const createSnapshot = async () => {
    if (!snapshotLabel.trim() || selectedScanIds.size === 0) return;
    setSnapshotting(true);
    try {
      const result = await workflowApi.createSnapshot(engId, snapshotLabel.trim(), [...selectedScanIds]);
      setComparison(result);
      setSnapshots(prev => [result.snapshot, ...prev]);
      setSnapshotLabel('');
      setSelectedScanIds(new Set());
      toast({ message: `Created scan snapshot with ${result.snapshot.observation_count} observations`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSnapshotting(false);
    }
  };

  return (
    <div className="space-y-6">
      <AIDraftWorkbench
        engId={engId}
        drafts={drafts}
        setDrafts={setDrafts}
        toast={toast}
        onFindingsChanged={onFindingsChanged}
      />
      <div className="card p-6" style={{ borderStyle: 'dashed' }}>
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="flex-1">
            <h3 className="text-sm font-semibold themed-text-primary mb-1">Upload Scan Data</h3>
            <p className="text-xs themed-text-muted">Nmap XML/text, Nessus, Burp XML, Nuclei JSONL, SARIF 2.1, or raw text.</p>
          </div>
          <div className="flex items-center gap-3">
            <select className="input-field text-sm w-28" value={scanType}
              onChange={(e) => setScanType(e.target.value)}>
              <option value="auto">Auto</option>
              <option value="nmap">Nmap</option>
              <option value="nessus">Nessus</option>
              <option value="burp">Burp</option>
              <option value="nuclei">Nuclei</option>
              <option value="sarif">SARIF</option>
              <option value="custom">Other</option>
            </select>
            <label className="btn-secondary flex items-center gap-2 cursor-pointer text-sm">
              <Upload size={14} />
              {uploading ? 'Uploading...' : 'Upload'}
              <input type="file" className="hidden" onChange={handleUpload} disabled={uploading} />
            </label>
          </div>
        </div>
        {scans.length > 0 && (
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
            <p className="text-[10px] themed-text-muted mb-2">First checkbox: include in AI analysis. Second checkbox: include in the next structured snapshot.</p>
            <div className="grid sm:grid-cols-[minmax(0,1fr)_10rem] gap-2 mb-3">
              <div className="relative">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
                <input className="input w-full pl-8 text-xs" value={scanQuery}
                  onChange={event => setScanQuery(event.target.value)}
                  placeholder="Filter uploaded scans" aria-label="Filter uploaded scans" />
              </div>
              <select className="input text-xs" value={scanListType} onChange={event => setScanListType(event.target.value)} aria-label="Filter scans by type">
                <option value="all">All types</option>
                <option value="nmap">Nmap</option><option value="nessus">Nessus</option>
                <option value="burp">Burp</option><option value="nuclei">Nuclei</option>
                <option value="sarif">SARIF</option><option value="custom">Other</option>
              </select>
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
              <button className="btn-ghost text-xs" onClick={() => setAnalysisScanIds(new Set(visibleScans.slice(0, 50).map(scan => scan.id)))}>Select first 50 matching for AI</button>
              <button className="btn-ghost text-xs" onClick={() => setAnalysisScanIds(new Set())}>Clear AI selection</button>
              <button className="btn-ghost text-xs" onClick={() => setSelectedScanIds(new Set(visibleScans.filter(scan => scan.scan_type !== 'custom').slice(0, 50).map(scan => scan.id)))}>Select matching snapshot</button>
              <button className="btn-ghost text-xs" onClick={() => setSelectedScanIds(new Set())}>Clear snapshot selection</button>
            </div>
            <div className="space-y-2">
              {visibleScans.map(s => (
                <div key={s.id} className="flex items-center gap-3 text-sm">
                  <input type="checkbox" checked={analysisScanIds.has(s.id)}
                    disabled={!analysisScanIds.has(s.id) && analysisScanIds.size >= 50}
                    title={!analysisScanIds.has(s.id) && analysisScanIds.size >= 50 ? 'Deselect another upload before adding this one' : 'Include this upload in the next AI analysis'}
                    aria-label={`Include ${s.filename} in AI analysis`}
                    onChange={() => setAnalysisScanIds(prev => {
                      const next = new Set(prev);
                      if (next.has(s.id)) next.delete(s.id); else next.add(s.id);
                      return next;
                    })} />
                  <input type="checkbox" checked={selectedScanIds.has(s.id)} disabled={s.scan_type === 'custom' || (!selectedScanIds.has(s.id) && selectedScanIds.size >= 50)}
                    title={s.scan_type === 'custom' ? 'Raw uploads cannot be included in structured scan snapshots' : (!selectedScanIds.has(s.id) && selectedScanIds.size >= 50) ? 'Deselect another upload before adding this one' : 'Include this upload in the next snapshot'}
                    aria-label={`Include ${s.filename} in snapshot`}
                    onChange={() => setSelectedScanIds(prev => {
                      const next = new Set(prev);
                      if (next.has(s.id)) next.delete(s.id); else next.add(s.id);
                      return next;
                    })} />
                  <FileText size={14} className="themed-text-muted" />
                  <span className="font-mono themed-text-secondary flex-1 min-w-0 truncate" title={s.filename}>{s.filename}</span>
                  <span className={`hidden md:inline text-[10px] font-mono ${s.stored_file_available ? 'themed-text-muted' : 'text-red-400'}`}>{formatFileSize(s.size_bytes)}</span>
                  {s.source_job_id && <span className="hidden lg:inline text-[10px] themed-text-muted">Tool Runner</span>}
                  {s.created_at && <time className="hidden xl:inline text-[10px] themed-text-muted" dateTime={s.created_at}>{new Date(s.created_at).toLocaleString()}</time>}
                  <span className="badge" style={{ backgroundColor: 'var(--bg-600)', color: 'var(--text-muted)' }}>
                    {s.scan_type}
                  </span>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!window.confirm(`Delete uploaded scan "${s.filename}"? Snapshots keep normalized observations, but the original file will be removed.`)) return;
                      try {
                        await analysisApi.deleteScan(engId, s.id);
                        setScans(prev => prev.filter(x => x.id !== s.id));
                        setAnalysisScanIds(prev => { const next = new Set(prev); next.delete(s.id); return next; });
                        setSelectedScanIds(prev => { const next = new Set(prev); next.delete(s.id); return next; });
                        toast({ message: `Deleted ${s.filename}`, type: 'success' });
                      } catch (err) {
                        toast({ message: err.message, type: 'error' });
                      }
                    }}
                    className="themed-text-muted hover:text-red-400 transition-colors p-1" title="Delete scan">
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
              {visibleScans.length === 0 && <p className="text-xs themed-text-muted py-4 text-center">No uploaded scans match this filter.</p>}
            </div>
          </div>
        )}
      </div>

      <div className="card p-6">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="flex-1">
            <label htmlFor="snapshot-label" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Scan Snapshot</label>
            <input id="snapshot-label" className="input-field text-sm" value={snapshotLabel}
              onChange={e => setSnapshotLabel(e.target.value)} placeholder="Baseline or Retest 1" />
            <p className="text-xs themed-text-muted mt-1">Select up to 50 structured uploads, with a combined limit of 250 MB.</p>
          </div>
          <button className="btn-secondary text-sm" onClick={createSnapshot}
            disabled={snapshotting || !snapshotLabel.trim() || selectedScanIds.size === 0}>
            {snapshotting ? 'Comparing...' : `Snapshot ${selectedScanIds.size} selected scan${selectedScanIds.size === 1 ? '' : 's'}`}
          </button>
        </div>
        {snapshots.length > 0 && <div className="mt-4 flex flex-wrap gap-2">
          {snapshots.map(snapshot => <button key={snapshot.id} className="btn-ghost text-xs"
            title={`${snapshot.parser_version} · ${new Date(snapshot.created_at).toLocaleString()}`}
            onClick={async () => {
              try { setComparison(await workflowApi.compareSnapshot(engId, snapshot.id)); }
              catch (err) { toast({ message: err.message, type: 'error' }); }
            }}>
            {snapshot.label} ({snapshot.observation_count})
          </button>)}
        </div>}
        {comparison && <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="col-span-2 sm:col-span-4 text-xs themed-text-muted">
            <span className="themed-text-primary font-medium">{comparison.snapshot.label}</span>
            {comparison.baseline
              ? ` compared with ${comparison.baseline.label}`
              : ' is the first versioned baseline'}
          </div>
          {comparison.warnings?.map(warning => (
            <div key={warning.code} className="col-span-2 sm:col-span-4 text-xs text-yellow-300 rounded p-3"
              style={{ backgroundColor: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.25)' }}>
              {warning.message}
            </div>
          ))}
          {comparison.detail_summary && Object.values(comparison.detail_summary.truncated).some(Boolean) && (
            <div className="col-span-2 sm:col-span-4 text-xs themed-text-muted">
              Detail rows are limited to {comparison.detail_summary.limit_per_status} per status; counts remain complete.
            </div>
          )}
          {Object.entries(comparison.counts).map(([status, count]) => (
            <div key={status} className="rounded p-3" style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
              <div className="text-xl font-mono themed-text-primary">{count}</div>
              <div className="text-xs uppercase tracking-wider themed-text-muted">{status}</div>
            </div>
          ))}
          <div className="col-span-2 sm:col-span-4 space-y-1">
            {[...comparison.regressed, ...comparison.new, ...comparison.resolved].map(item => (
              <div key={`${item.status}-${item.fingerprint}`} className="text-xs flex gap-2 rounded p-2" style={{ backgroundColor: 'var(--bg-800)' }}>
                <span className={item.status === 'regressed' ? 'text-red-400' : item.status === 'new' ? 'text-yellow-400' : 'text-green-400'}>{item.status.toUpperCase()}</span>
                <span className="themed-text-primary">{item.title}</span>
                <span className="themed-text-muted">{item.host}{item.port != null ? `:${item.port}` : ''}</span>
              </div>
            ))}
          </div>
        </div>}
      </div>

      <div className="card p-6">
        {analysisPreview && (
          <div className={`mb-4 rounded-md border px-3 py-2 ${analysisPreview.ready ? 'border-green-500/30 bg-green-500/5' : 'border-yellow-500/40 bg-yellow-500/5'}`} role="status">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <span className="themed-text-primary font-medium">AI input preflight</span>
              <span className="themed-text-secondary">{analysisPreview.scan_count} / {analysisPreview.max_scan_count} files</span>
              <span className="themed-text-secondary">
                {analysisPreview.total_bytes_complete ? '' : 'at least '}{(analysisPreview.total_bytes / (1024 * 1024)).toFixed(1)} / {(analysisPreview.max_total_bytes / (1024 * 1024)).toFixed(0)} MB
              </span>
              <span className="themed-text-secondary">Provider: {analysisPreview.provider}</span>
              <span className={analysisPreview.redaction_enabled ? 'text-green-400' : 'text-yellow-400'}>
                Local secret redaction {analysisPreview.redaction_enabled ? 'on' : 'off'}
              </span>
            </div>
            {analysisPreview.issues.map(issue => <p key={issue} className="text-xs text-yellow-300 mt-1">{issue}</p>)}
            {analysisPreview.ready && <p className="text-[10px] themed-text-muted mt-1">Ready for review proposals. Provider connectivity is checked only when analysis starts.</p>}
          </div>
        )}
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Brain size={16} className="text-cyan-400" />
              <h3 className="text-sm font-semibold themed-text-primary">AI Analysis</h3>
            </div>
            <p className="text-xs themed-text-muted">
              Analyze up to 50 uploaded scans and 250 MB of combined input to generate review proposals. Common credentials are redacted locally by default, and nothing enters Findings until you accept it.
            </p>
          </div>
          <button onClick={handleAnalyze} disabled={analyzing || !analysisPreview?.ready}
            className="btn-primary flex items-center gap-2 whitespace-nowrap">
            {analyzing ? <Spinner className="w-4 h-4" /> : <Zap size={16} />}
            {analyzing ? 'Analyzing...' : `Run Analysis (${analysisScanIds.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}


// Collapsible narrative display
function CollapsibleNarrative({ narrative, toast, onDelete }) {
  const [open, setOpen] = useState(false);
  if (!narrative || !narrative.full_narrative) return null;

  return (
    <div className="card overflow-hidden mb-4">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
        onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
        onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
        {open ? <ChevronDown size={16} className="themed-text-muted" /> : <ChevronRight size={16} className="themed-text-muted" />}
        <BookOpen size={16} style={{ color: '#8b5cf6' }} />
        <h3 className="text-sm font-semibold themed-text-primary uppercase tracking-wider flex-1">Attack Narrative</h3>
        {narrative.overall_risk && <SeverityBadge severity={narrative.overall_risk} />}
        <span onClick={(e) => {
          e.stopPropagation();
          navigator.clipboard.writeText(narrative.full_narrative);
          toast({ message: 'Narrative copied to clipboard', type: 'success' });
        }} className="text-xs font-mono px-2 py-1 rounded themed-text-muted cursor-pointer" style={{ backgroundColor: 'var(--bg-600)' }}>
          Copy
        </span>
        <span onClick={(e) => {
          e.stopPropagation();
          if (onDelete) onDelete();
        }} className="text-xs font-mono px-2 py-1 rounded cursor-pointer" style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#ef4444' }} title="Delete narrative">
          <Trash2 size={12} />
        </span>
      </button>
      {open && (
        <div className="px-5 pb-5" style={{ borderTop: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}>
          {narrative.executive_summary && (
            <div className="px-4 py-3 rounded-lg my-4" style={{ backgroundColor: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)' }}>
              <p className="text-xs font-mono uppercase tracking-wider mb-1" style={{ color: '#8b5cf6' }}>Executive Summary</p>
              <p className="text-sm themed-text-secondary">{narrative.executive_summary}</p>
            </div>
          )}
          <div className="prose prose-sm max-w-none themed-text-secondary text-sm leading-relaxed whitespace-pre-wrap"
            style={{ fontFamily: 'inherit' }}>
            {narrative.full_narrative}
          </div>
          {narrative.mitre_techniques && narrative.mitre_techniques.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <p className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-2">MITRE ATT&CK Techniques</p>
              <div className="flex flex-wrap gap-2">
                {narrative.mitre_techniques.map((t, i) => (
                  <a key={i} href={`https://attack.mitre.org/techniques/${(t.technique_id || '').replace('.', '/')}/`}
                    target="_blank" rel="noopener noreferrer"
                    className="text-xs font-mono px-2 py-1 rounded transition-colors"
                    style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)', border: '1px solid rgba(239,68,68,0.2)' }}>
                    {t.technique_id} {t.technique_name}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Exploitation Chains tab (formerly Attack Paths)
function AttackPathsTab({ engId, toast, fullNarrative, setFullNarrative }) {
  const [paths, setPaths] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [expanded, setExpanded] = useState(new Set());
  const [generatingNarrative, setGeneratingNarrative] = useState(false);

  const toggleExpanded = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  useEffect(() => {
    apApi.list(engId).then(data => {
      setPaths(data);
      const withNarrative = new Set(data.filter(p => p.narrative).map(p => p.id));
      if (withNarrative.size > 0) setExpanded(withNarrative);
    }).catch((err) => {
      toast({ message: `Could not load exploitation chains: ${err.message}`, type: 'error' });
    }).finally(() => setLoading(false));
    // Load the saved full narrative once for this engagement.
    narrativeApi.getSaved(engId).then(saved => {
      setFullNarrative(saved || null);
    }).catch((err) => {
      toast({ message: `Could not load the saved attack narrative: ${err.message}`, type: 'error' });
    });
  }, [engId, setFullNarrative, toast]);

  const handleGenerate = async () => {
    if (paths.length > 0) {
      const confirmed = window.confirm(
        `This will replace the existing ${paths.length} exploitation chain(s) with a fresh analysis based on current findings. Continue?`
      );
      if (!confirmed) return;
    }
    setGenerating(true);
    setFullNarrative(null);
    try {
      await narrativeApi.deleteFull(engId);
      const result = await apApi.generate(engId);
      setPaths(result);
      toast({ message: `Generated ${result.length} exploitation chains`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;

  // Get the most recent generated timestamp
  const lastGenerated = paths.length > 0 && paths[0].created_at
    ? new Date(paths[0].created_at).toLocaleString()
    : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          {lastGenerated && (
            <span className="text-xs font-mono themed-text-muted">
              Last generated: {lastGenerated}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {paths.length > 0 && (
            <button onClick={async () => {
              const confirmed = window.confirm(`Clear all ${paths.length} exploitation chain(s)?`);
              if (!confirmed) return;
              try {
                await apApi.clear(engId);
                await narrativeApi.deleteFull(engId);
                setPaths([]);
                setFullNarrative(null);
                toast({ message: 'Exploitation chains and narrative cleared', type: 'success' });
              } catch (err) {
                toast({ message: err.message, type: 'error' });
              }
            }} className="btn-secondary flex items-center gap-2 text-sm">
              <Trash2 size={14} /> Clear
            </button>
          )}
          <button onClick={handleGenerate} disabled={generating}
            className="btn-primary flex items-center gap-2 text-sm">
            {generating ? <Spinner className="w-4 h-4" /> : <Route size={14} />}
            {generating ? 'Generating...' : paths.length > 0 ? 'Regenerate Chains' : 'Generate Exploitation Chains'}
          </button>
          {paths.length > 0 && (
            <button onClick={async () => {
              setGeneratingNarrative(true);
              try {
                const result = await narrativeApi.generateFull(engId);
                await narrativeApi.saveFull(engId, result);
                setFullNarrative(result);
                toast({ message: 'Attack narrative generated and saved', type: 'success' });
              } catch (err) { toast({ message: err.message, type: 'error' }); }
              finally { setGeneratingNarrative(false); }
            }} disabled={generatingNarrative}
              className="btn-secondary flex items-center gap-2 text-sm">
              {generatingNarrative ? <Spinner className="w-4 h-4" /> : <BookOpen size={14} />}
              {generatingNarrative ? 'Writing...' : 'Generate Narrative'}
            </button>
          )}
        </div>
      </div>

      {/* Full Engagement Narrative */}
      <CollapsibleNarrative narrative={fullNarrative} toast={toast} onDelete={async () => {
        try {
          await narrativeApi.deleteFull(engId);
          setFullNarrative(null);
          toast({ message: 'Narrative deleted', type: 'success' });
        } catch (err) {
          toast({ message: `Could not delete the narrative: ${err.message}`, type: 'error' });
        }
      }} />

      {paths.length === 0 ? (
        <EmptyState
          icon={Route}
          title="No exploitation chains"
          description="Generate exploitation chains to map how findings connect into realistic attack scenarios."
        />
      ) : (
        <div className="space-y-3">
          {paths.map(path => (
            <div key={path.id} className="card overflow-hidden">
              <button
                onClick={() => toggleExpanded(path.id)}
                className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
                onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                {expanded.has(path.id) ?
                  <ChevronDown size={16} className="themed-text-muted" /> :
                  <ChevronRight size={16} className="themed-text-muted" />
                }
                <div className="flex-1 min-w-0">
                  <span className="font-medium themed-text-primary">{path.name}</span>
                  {(() => {
                    const match = path.description?.match(/^\[Targets:\s*([^\]]+)\]/);
                    if (match) {
                      return (
                        <div className="text-xs font-mono themed-text-muted mt-0.5">
                          Targets: {match[1]}
                        </div>
                      );
                    }
                    const allText = (path.steps || []).map(s => `${s.title || ''} ${s.description || ''} ${s.finding_title || ''}`).join(' ');
                    const hosts = allText.match(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|[A-Za-z0-9-]+\.(local|com|net|org|io)\b/gi);
                    const unique = hosts ? [...new Set(hosts)] : [];
                    return unique.length > 0 ? (
                      <div className="text-xs font-mono themed-text-muted mt-0.5">
                        Targets: {unique.join(', ')}
                      </div>
                    ) : null;
                  })()}
                </div>
                {path.risk_level && <SeverityBadge severity={path.risk_level} />}
                <span onClick={(e) => {
                  e.stopPropagation();
                  const text = [
                    path.name,
                    path.description?.replace(/^\[Targets:[^\]]*\]\n*/i, ''),
                    ...(path.steps || []).map((s, i) => `Step ${s.order || i+1}: ${s.title}\n${s.description || ''}`),
                    path.narrative || '',
                  ].filter(Boolean).join('\n\n');
                  navigator.clipboard.writeText(text);
                  toast({ message: 'Chain copied to clipboard', type: 'success' });
                }} className="text-xs font-mono px-2 py-1 rounded themed-text-muted cursor-pointer shrink-0" style={{ backgroundColor: 'var(--bg-600)' }} title="Copy chain">
                  Copy
                </span>
                <span onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm('Delete this exploitation chain?')) {
                    apApi.clear(engId).then(() => {
                      setPaths(prev => prev.filter(p => p.id !== path.id));
                      toast({ message: 'Chain deleted', type: 'success' });
                    }).catch(err => toast({ message: err.message, type: 'error' }));
                  }
                }} className="text-xs font-mono px-2 py-1 rounded cursor-pointer shrink-0" style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#ef4444' }} title="Delete chain">
                  <Trash2 size={12} />
                </span>
              </button>
              {expanded.has(path.id) && (
                <div className="px-5 pb-5 pt-1" style={{ borderTop: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}>
                  {path.narrative && (
                    <div className="mb-4 px-4 py-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <BookOpen size={14} style={{ color: '#8b5cf6' }} />
                        <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#8b5cf6' }}>Narrative</span>
                      </div>
                      <div className="text-sm themed-text-secondary whitespace-pre-wrap leading-relaxed">{path.narrative}</div>
                      {path.mitre_techniques && path.mitre_techniques.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                          {path.mitre_techniques.map((t, i) => (
                            <a key={i} href={`https://attack.mitre.org/techniques/${(t.technique_id || '').replace('.', '/')}/`}
                              target="_blank" rel="noopener noreferrer"
                              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                              style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--accent-red)', border: '1px solid rgba(239,68,68,0.2)' }}>
                              {t.technique_id}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {path.description && !path.narrative && (
                    <p className="text-sm themed-text-secondary mb-4">
                      {path.description.replace(/^\[Targets:[^\]]*\]\n*/i, '')}
                    </p>
                  )}
                  {path.steps && Array.isArray(path.steps) && (
                    <div className="space-y-3 ml-4">
                      {path.steps.map((step, i) => (
                        <div key={i} className="flex gap-3">
                          <div className="flex flex-col items-center">
                            <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono font-bold"
                              style={{ backgroundColor: 'rgba(239,68,68,0.15)', color: 'var(--accent-red)' }}>
                              {step.order || i + 1}
                            </div>
                            {i < path.steps.length - 1 && <div className="w-px h-full mt-1" style={{ backgroundColor: 'var(--bg-500)' }} />}
                          </div>
                          <div className="pb-4">
                            <p className="text-sm font-medium themed-text-primary">{step.title}</p>
                            <p className="text-xs themed-text-muted mt-0.5">{step.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Reports tab
function ReportsTab({ engId, toast }) {
  const [reportList, setReportList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reportFormat, setReportFormat] = useState('docx');
  const [useAI, setUseAI] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [showTemplateForm, setShowTemplateForm] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [templateForm, setTemplateForm] = useState({
    name: '', company_name: '', primary_color: '#dc2626', secondary_color: '#1a1a25',
    header_text: '', footer_text: '', is_default: false,
  });
  const [logoFile, setLogoFile] = useState(null);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [readiness, setReadiness] = useState(null);
  const [redactSarif, setRedactSarif] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [reports, tmpls, readinessResult] = await Promise.all([
          reportsApi.list(engId),
          templatesApi.list(),
          workflowApi.readiness(engId),
        ]);
        setReportList(reports);
        setTemplates(tmpls);
        setReadiness(readinessResult);
        const def = tmpls.find(t => t.is_default);
        if (def) setSelectedTemplate(def.id);
      } catch (e) {
        toast({ message: `Could not load reports: ${e.message}`, type: 'error' });
      }
      finally { setLoading(false); }
    })();
  }, [engId]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const templateId = reportFormat === 'docx' && selectedTemplate ? selectedTemplate : null;
      const report = await reportsApi.generate(engId, reportFormat, templateId, useAI);
      setReportList(prev => [report, ...prev]);
      const fellBack = report.format !== reportFormat;
      toast({
        message: `${report.format.toUpperCase()} report generated${useAI ? ' with AI enhancement' : ' locally'}${report.template_used ? ` with "${report.template_used}" template` : ''}${fellBack ? ' (Word generation was unavailable)' : ''}`,
        type: fellBack ? 'info' : 'success',
      });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveTemplate = async () => {
    setSavingTemplate(true);
    try {
      const formData = new FormData();
      Object.entries(templateForm).forEach(([k, v]) => formData.append(k, v));
      if (logoFile) formData.append('logo', logoFile);

      let result;
      if (editingTemplate) {
        result = await templatesApi.update(editingTemplate.id, formData);
      } else {
        result = await templatesApi.create(formData);
      }
      const tmpls = await templatesApi.list();
      setTemplates(tmpls);
      const defaultTemplate = tmpls.find(t => t.is_default);
      if (defaultTemplate && (result.is_default || !selectedTemplate)) {
        setSelectedTemplate(defaultTemplate.id);
      }
      setShowTemplateForm(false);
      setEditingTemplate(null);
      setLogoFile(null);
      setTemplateForm({ name: '', company_name: '', primary_color: '#dc2626', secondary_color: '#1a1a25', header_text: '', footer_text: '', is_default: false });
      toast({ message: editingTemplate ? 'Template updated' : 'Template created', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleDeleteTemplate = async (id) => {
    const confirmed = window.confirm('Delete this report template?');
    if (!confirmed) return;
    try {
      await templatesApi.delete(id);
      setTemplates(prev => prev.filter(t => t.id !== id));
      if (selectedTemplate === id) setSelectedTemplate('');
      toast({ message: 'Template deleted', type: 'success' });
    } catch (err) { toast({ message: err.message, type: 'error' }); }
  };

  const startEditTemplate = (t) => {
    setEditingTemplate(t);
    setTemplateForm({
      name: t.name, company_name: t.company_name || '', primary_color: t.primary_color || '#dc2626',
      secondary_color: t.secondary_color || '#1a1a25', header_text: t.header_text || '',
      footer_text: t.footer_text || '', is_default: t.is_default,
    });
    setShowTemplateForm(true);
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
  const defaultTemplate = templates.find(t => t.is_default);

  return (
    <div>
      {readiness && <div className="card p-5 mb-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="text-2xl font-mono themed-text-primary">{readiness.score}</div>
          <div className="flex-1">
            <div className="text-sm font-semibold themed-text-primary">Report readiness</div>
            <div className={`text-xs ${readiness.ready ? 'text-green-400' : 'text-red-400'}`}>
              {readiness.ready ? 'Ready to generate. Review warnings before delivery.' : `${readiness.blockers.length} blocker${readiness.blockers.length === 1 ? '' : 's'} should be resolved.`}
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs themed-text-muted">
            <input type="checkbox" checked={redactSarif} onChange={event => setRedactSarif(event.target.checked)} />
            Redact common secrets
          </label>
          <button className="btn-secondary text-xs flex items-center gap-1" onClick={async () => {
            try { await workflowApi.downloadSarif(engId, redactSarif); toast({ message: `${redactSarif ? 'Redacted ' : ''}SARIF export downloaded`, type: 'success' }); }
            catch (err) { toast({ message: err.message, type: 'error' }); }
          }}><Download size={12} /> Export SARIF</button>
        </div>
        {(readiness.blockers.length > 0 || readiness.warnings.length > 0) && <div className="mt-3 space-y-1">
          {[...readiness.blockers, ...readiness.warnings].map(item => (
            <div key={item.code} className="text-xs themed-text-muted">{readiness.blockers.includes(item) ? 'Blocker' : 'Warning'}: {item.message}</div>
          ))}
        </div>}
      </div>}
      {/* Template management */}
      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Palette size={16} className="themed-text-muted" />
            <span className="text-sm font-semibold themed-text-primary">Report Templates</span>
          </div>
          <button onClick={() => { setEditingTemplate(null); setTemplateForm({ name: '', company_name: '', primary_color: '#dc2626', secondary_color: '#1a1a25', header_text: '', footer_text: '', is_default: false }); setLogoFile(null); setShowTemplateForm(!showTemplateForm); }}
            className="btn-ghost text-xs flex items-center gap-1">
            <Plus size={12} /> {showTemplateForm ? 'Cancel' : 'New Template'}
          </button>
        </div>

        {/* Template list */}
        {templates.length > 0 && !showTemplateForm && (
          <div className="space-y-2 mb-3">
            {templates.map(t => (
              <div key={t.id} className="flex items-center gap-3 px-3 py-2 rounded-md"
                style={{ backgroundColor: selectedTemplate === t.id ? 'rgba(239,68,68,0.08)' : 'var(--bg-700)',
                         border: `1px solid ${selectedTemplate === t.id ? 'rgba(239,68,68,0.3)' : 'var(--bg-500)'}` }}>
                <button onClick={() => setSelectedTemplate(t.id)} className="flex items-center gap-3 flex-1 text-left">
                  <div className="w-5 h-5 rounded-sm border" style={{ backgroundColor: t.primary_color, borderColor: t.primary_color + '60' }} />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm themed-text-primary">{t.name}</span>
                    {t.company_name && <span className="text-xs themed-text-muted ml-2">{t.company_name}</span>}
                  </div>
                  {t.is_default && <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>DEFAULT</span>}
                  {t.has_logo && <span className="text-[10px] font-mono themed-text-muted">LOGO</span>}
                </button>
                <button aria-label={`Edit ${t.name}`} onClick={() => startEditTemplate(t)} className="themed-text-muted hover:text-white transition-colors p-1"><Edit3 size={12} /></button>
                <button aria-label={`Delete ${t.name}`} onClick={() => handleDeleteTemplate(t.id)} className="themed-text-muted hover:text-red-400 transition-colors p-1"><Trash2 size={12} /></button>
              </div>
            ))}
          </div>
        )}

        {templates.length === 0 && !showTemplateForm && (
          <p className="text-xs themed-text-muted">No templates yet. Reports will use default Breachwright branding.</p>
        )}

        {/* Template form */}
        {showTemplateForm && (
          <div className="space-y-3 mt-3 p-4 rounded-md" style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="template-name" className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Template Name *</label>
                <input id="template-name" className="input-field text-sm" value={templateForm.name} onChange={e => setTemplateForm(p => ({ ...p, name: e.target.value }))} placeholder="Client Report Template" />
              </div>
              <div>
                <label htmlFor="template-company-name" className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Company Name</label>
                <input id="template-company-name" className="input-field text-sm" value={templateForm.company_name} onChange={e => setTemplateForm(p => ({ ...p, company_name: e.target.value }))} placeholder="Acme Security Inc." />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="template-primary-color" className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Primary Color</label>
                <div className="flex items-center gap-2">
                  <input aria-label="Primary color picker" type="color" value={templateForm.primary_color} onChange={e => setTemplateForm(p => ({ ...p, primary_color: e.target.value }))} className="w-8 h-8 rounded cursor-pointer" style={{ border: 'none', padding: 0 }} />
                  <input id="template-primary-color" className="input-field text-sm font-mono flex-1" value={templateForm.primary_color} onChange={e => setTemplateForm(p => ({ ...p, primary_color: e.target.value }))} />
                </div>
              </div>
              <div>
                <p className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Logo</p>
                <label className="btn-secondary text-xs cursor-pointer inline-flex items-center gap-1">
                  <Upload size={12} /> {logoFile ? logoFile.name : editingTemplate?.has_logo ? 'Replace Logo' : 'Upload Logo'}
                  <input type="file" className="hidden" accept=".png,.jpg,.jpeg" onChange={e => setLogoFile(e.target.files[0])} />
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="template-report-header" className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Report Header</label>
                <input id="template-report-header" className="input-field text-sm" value={templateForm.header_text} onChange={e => setTemplateForm(p => ({ ...p, header_text: e.target.value }))} placeholder="PENETRATION TEST REPORT" />
              </div>
              <div>
                <label htmlFor="template-report-footer" className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Report Footer</label>
                <input id="template-report-footer" className="input-field text-sm" value={templateForm.footer_text} onChange={e => setTemplateForm(p => ({ ...p, footer_text: e.target.value }))} placeholder="CONFIDENTIAL" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="is_default" checked={templateForm.is_default} onChange={e => setTemplateForm(p => ({ ...p, is_default: e.target.checked }))} />
              <label htmlFor="is_default" className="text-xs themed-text-secondary">Set as default template</label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => { setShowTemplateForm(false); setEditingTemplate(null); }} className="btn-ghost text-xs">Cancel</button>
              <button onClick={handleSaveTemplate} disabled={savingTemplate || !templateForm.name.trim()}
                className="btn-primary text-xs flex items-center gap-1">
                {savingTemplate ? <Spinner className="w-3 h-3" /> : <Check size={12} />}
                {editingTemplate ? 'Update' : 'Save'} Template
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Generate controls */}
      <div className="flex flex-wrap items-center justify-end gap-3 mb-4">
        <label className="flex items-center gap-2 text-xs themed-text-secondary">
          <input
            type="checkbox"
            checked={useAI}
            onChange={e => setUseAI(e.target.checked)}
          />
          Enhance with configured AI
        </label>
        {reportFormat === 'docx' && templates.length > 0 && (
          <select aria-label="Report template" className="input-field text-sm" style={{ maxWidth: 200 }} value={selectedTemplate}
            onChange={e => setSelectedTemplate(e.target.value)}>
            <option value="">{defaultTemplate ? `Automatic: ${defaultTemplate.name}` : 'Breachwright Default'}</option>
            {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        )}
        <select aria-label="Report format" className="input-field text-sm w-28" value={reportFormat}
          onChange={(e) => setReportFormat(e.target.value)}>
          <option value="docx">DOCX</option>
          <option value="md">Markdown</option>
        </select>
        <button onClick={handleGenerate} disabled={generating}
          className="btn-primary flex items-center gap-2 text-sm">
          {generating ? <Spinner className="w-4 h-4" /> : <FileText size={14} />}
          {generating ? 'Generating...' : 'Generate Report'}
        </button>
      </div>

      {reportList.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No reports"
          description="Generate a professional penetration testing report from your findings and exploitation chains."
        />
      ) : (
        <div className="space-y-2">
          {reportList.map(report => (
            <div key={report.id} className="card flex items-center gap-4 px-5 py-4">
              <FileText size={18} className="themed-text-muted" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium themed-text-primary truncate">{report.title}</p>
                <p className="text-xs themed-text-muted font-mono">
                  {report.format.toUpperCase()}
                  {report.template_used && ` // ${report.template_used}`}
                  {report.created_at && ` // ${new Date(report.created_at).toLocaleString()}`}
                </p>
              </div>
              <button
                onClick={async () => {
                  if (!window.confirm(`Delete generated report "${report.title}"? The stored ${report.format.toUpperCase()} file will be removed.`)) return;
                  try {
                    await reportsApi.download(report.id, report.format, report.title);
                    toast({ message: `Downloaded: ${report.title}.${report.format}`, type: 'success' });
                  } catch (err) {
                    toast({ message: err.message, type: 'error' });
                  }
                }}
                className="btn-ghost flex items-center gap-1.5 text-sm"
              >
                <Download size={14} />
                Download
              </button>
              <button
                onClick={async () => {
                  try {
                    await reportsApi.delete(report.id);
                    setReportList(prev => prev.filter(r => r.id !== report.id));
                    toast({ message: 'Report deleted', type: 'success' });
                  } catch (err) {
                    toast({ message: err.message, type: 'error' });
                  }
                }}
                className="themed-text-muted hover:text-red-400 transition-colors p-2" title="Delete report">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Active Directory tab
function ADTab({ engId, toast, onFindingsCreated }) {
  const [imports, setImports] = useState([]);
  const [summary, setSummary] = useState(null);
  const [paths, setPaths] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [expanded, setExpanded] = useState(new Set());

  const toggleExpanded = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  useEffect(() => {
    (async () => {
      try {
        const [imp, sum, p] = await Promise.all([
          adApi.listImports(engId),
          adApi.summary(engId),
          adApi.paths(engId),
        ]);
        setImports(imp);
        setSummary(sum);
        setPaths(p);
      } catch (e) {
        toast({ message: `Could not load Active Directory data: ${e.message}`, type: 'error' });
      }
      finally { setLoading(false); }
    })();
  }, [engId]);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await adApi.import(engId, file);
      toast({ message: `Imported ${result.object_count} objects, ${result.relationship_count} relationships from ${result.domain || 'unknown domain'}`, type: 'success' });
      // Reload
      const [imp, sum] = await Promise.all([adApi.listImports(engId), adApi.summary(engId)]);
      setImports(imp);
      setSummary(sum);
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleAnalyze = async () => {
    if (paths.length > 0) {
      const confirmed = window.confirm(`This will replace the existing ${paths.length} AD attack path(s). Continue?`);
      if (!confirmed) return;
    }
    setAnalyzing(true);
    try {
      const result = await adApi.analyze(engId);
      setPaths(result.paths || []);
      toast({
        message: `Identified ${result.paths?.length || 0} grounded AD attack path${result.paths?.length === 1 ? '' : 's'} and prepared ${result.drafts_created || 0} finding proposal${result.drafts_created === 1 ? '' : 's'} for review in Scans`,
        type: 'success',
      });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDeleteImport = async (importId) => {
    try {
      await adApi.deleteImport(engId, importId);
      setImports(prev => prev.filter(i => i.id !== importId));
      const sum = await adApi.summary(engId);
      setSummary(sum);
      setPaths([]);
      toast({ message: 'Import deleted', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;

  const NODE_COLORS = {
    user: '#3b82f6',
    computer: '#22c55e',
    group: '#f97316',
    domain: '#dc2626',
    ou: '#8b5cf6',
    gpo: '#06b6d4',
  };

  return (
    <div className="space-y-6">
      {/* Import section */}
      <div className="card p-6" style={{ borderStyle: 'dashed' }}>
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Network size={16} className="text-blue-400" />
              <h3 className="text-sm font-semibold themed-text-primary">SharpHound / BloodHound Import</h3>
            </div>
            <p className="text-xs themed-text-muted">
              Upload a SharpHound or BloodHound.py ZIP file to import Active Directory objects and relationships.
            </p>
          </div>
          <label className="btn-secondary flex items-center gap-2 cursor-pointer text-sm">
            <Upload size={14} />
            {uploading ? 'Importing...' : 'Upload ZIP'}
            <input type="file" className="hidden" accept=".zip" onChange={handleUpload} disabled={uploading} />
          </label>
        </div>

        {imports.length > 0 && (
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
            {imports.map(imp => (
              <div key={imp.id} className="flex items-center gap-3 text-sm py-1.5">
                <Network size={14} className="themed-text-muted" />
                <span className="font-mono themed-text-secondary flex-1">
                  {imp.filename}
                  <span className="themed-text-muted ml-2">
                    ({imp.domain || 'unknown'}, {imp.object_count} objects, {imp.relationship_count} relationships)
                  </span>
                </span>
                <button onClick={() => handleDeleteImport(imp.id)}
                  className="themed-text-muted hover:text-red-400 transition-colors p-1">
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Summary stats */}
      {summary?.has_data && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold themed-text-primary mb-3">
            Domain: <span className="text-blue-400 font-mono">{summary.domain}</span>
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
            {Object.entries(summary.object_counts || {}).map(([type, count]) => (
              <div key={type} className="text-center p-3 rounded" style={{ backgroundColor: 'var(--bg-700)' }}>
                <div className="text-lg font-bold font-mono themed-text-primary">{count}</div>
                <div className="text-xs themed-text-muted uppercase">{type}s</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-4 text-xs">
            {summary.kerberoastable > 0 && (
              <span className="badge border bg-orange-500/15 text-orange-400 border-orange-500/30">
                {summary.kerberoastable} Kerberoastable
              </span>
            )}
            {summary.asrep_roastable > 0 && (
              <span className="badge border bg-yellow-500/15 text-yellow-400 border-yellow-500/30">
                {summary.asrep_roastable} AS-REP Roastable
              </span>
            )}
          </div>
        </div>
      )}

      {/* AI Analysis */}
      {summary?.has_data && (
        <div className="card p-6">
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <Brain size={16} className="text-cyan-400" />
                <h3 className="text-sm font-semibold themed-text-primary">AD Path Analysis</h3>
              </div>
              <p className="text-xs themed-text-muted">
                AI analyzes the imported AD data to identify critical attack paths to Domain Admin and other high-value targets.
              </p>
            </div>
            <button onClick={handleAnalyze} disabled={analyzing}
              className="btn-primary flex items-center gap-2 whitespace-nowrap">
              {analyzing ? <Spinner className="w-4 h-4" /> : <Zap size={16} />}
              {analyzing ? 'Analyzing...' : paths.length > 0 ? 'Reanalyze Paths' : 'Analyze AD Paths'}
            </button>
          </div>
        </div>
      )}

      {/* Attack Paths */}
      {paths.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold themed-text-primary mb-3">
            AD Attack Paths ({paths.length})
          </h3>
          <div className="space-y-3">
            {paths.map(path => (
              <div key={path.id} className="card overflow-hidden">
                <button
                  onClick={() => toggleExpanded(path.id)}
                  className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  {expanded.has(path.id) ?
                    <ChevronDown size={16} className="themed-text-muted" /> :
                    <ChevronRight size={16} className="themed-text-muted" />
                  }
                  <div className="flex-1 min-w-0">
                    <span className="font-medium themed-text-primary">{path.name}</span>
                    {path.path_nodes && Array.isArray(path.path_nodes) && (() => {
                      const targets = path.path_nodes
                        .filter(n => ['computer', 'domain'].includes(n.type))
                        .map(n => n.name);
                      const allNodes = path.path_nodes.map(n => n.name).join(' ');
                      const ips = allNodes.match(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g) || [];
                      const combined = [...new Set([...targets, ...ips])];
                      return combined.length > 0 ? (
                        <div className="text-xs font-mono themed-text-muted mt-0.5">
                          Targets: {combined.join(', ')}
                        </div>
                      ) : (
                        <div className="text-xs font-mono themed-text-muted mt-0.5">
                          Domain: {path.path_nodes.find(n => n.name?.includes('@'))?.name?.split('@')[1] || 'N/A'}
                        </div>
                      );
                    })()}
                  </div>
                  <SeverityBadge severity={path.risk_level || 'medium'} />
                </button>

                {expanded.has(path.id) && (
                  <div className="px-5 pb-5 pt-1" style={{ borderTop: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}>
                    {path.description && (
                      <p className="text-sm themed-text-secondary mb-4">{path.description}</p>
                    )}

                    {/* Graph visualization */}
                    {path.path_nodes && Array.isArray(path.path_nodes) && path.path_nodes.length > 0 && (
                      <ADPathGraph path={path} />
                    )}

                    {/* Step details */}
                    {path.path_nodes && Array.isArray(path.path_nodes) && (
                      <div className="space-y-2 ml-2 mb-4">
                        {path.path_nodes.map((node, i) => (
                          <div key={i} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono font-bold shrink-0"
                                style={{
                                  backgroundColor: (NODE_COLORS[node.type] || '#6b7280') + '20',
                                  color: NODE_COLORS[node.type] || '#6b7280',
                                }}>
                                {i + 1}
                              </div>
                              {i < path.path_nodes.length - 1 && (
                                <div className="w-px flex-1 mt-1" style={{ backgroundColor: 'var(--bg-500)' }} />
                              )}
                            </div>
                            <div className="pb-3">
                              <p className="text-sm font-medium themed-text-primary">
                                {node.name}
                                <span className="text-xs themed-text-muted ml-2">({node.type})</span>
                              </p>
                              {node.technique && (
                                <p className="text-xs themed-text-muted mt-0.5">{node.technique}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Remediation */}
                    {path.remediation && (
                      <div className="mt-3 p-3 rounded" style={{ backgroundColor: 'var(--bg-700)' }}>
                        <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-1.5">
                          Remediation
                        </span>
                        <p className="text-sm themed-text-secondary whitespace-pre-wrap">{path.remediation}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state when no data */}
      {!summary?.has_data && imports.length === 0 && (
        <EmptyState
          icon={Network}
          title="No Active Directory data"
          description="Upload a SharpHound or BloodHound.py ZIP file to start analyzing AD attack paths."
        />
      )}
    </div>
  );
}

// Main engagement detail page
export default function EngagementDetail() {
  const canEdit = true;
  const { id } = useParams();
  const navigate = useNavigate();
  const [engagement, setEngagement] = useState(null);
  const [findingsList, setFindingsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [fullNarrative, setFullNarrative] = useState(null);
  const [toastData, setToastData] = useState(null);

  const toast = useCallback((data) => setToastData(data), []);
  useEffect(() => {
    (async () => {
      try {
        const [eng, f] = await Promise.all([engApi.get(id), findingsApi.list(id)]);
        setEngagement(eng);
        setFindingsList(f);
      } catch (err) {
        toast({ message: err.message, type: 'error' });
      } finally {
        setLoading(false);
      }
    })();
  }, [id, toast]);

  const handleFindingsChanged = async () => {
    const updated = await findingsApi.list(id);
    setFindingsList(updated);
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Spinner className="w-6 h-6" style={{ color: 'var(--accent-red)' }} /></div>;
  }

  if (!engagement) {
    return <div className="text-center py-20 themed-text-muted">Engagement not found.</div>;
  }

  const sevCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  findingsList.forEach(f => { sevCounts[f.severity] = (sevCounts[f.severity] || 0) + 1; });
  const activeRetestCount = findingsList.filter(f => ['open', 'retest_needed'].includes(f.retest_status)).length;

  return (
    <div className="animate-fade-in">
      <button onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-sm themed-text-muted transition-colors mb-5"
        onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}>
        <ArrowLeft size={16} /> Back to Engagements
      </button>

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold themed-text-primary">{engagement.name}</h1>
            <StatusBadge status={engagement.status} />
          </div>
          <p className="text-sm themed-text-muted">
            {engagement.client_name}
            {engagement.scope && <span className="opacity-60"> // {engagement.scope}</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          {/* Status transitions */}
          {canEdit && engagement.status === 'active' && (
            <button onClick={async () => {
              try {
                await engApi.update(id, { status: 'completed' });
                setEngagement(prev => ({ ...prev, status: 'completed' }));
                toast({ message: 'Engagement marked as completed', type: 'success' });
              } catch (err) { toast({ message: err.message, type: 'error' }); }
            }} className="btn-secondary flex items-center gap-2 text-sm">
              <Check size={14} /> Complete
            </button>
          )}
          {canEdit && engagement.status === 'completed' && (
            <button onClick={async () => {
              try {
                await engApi.update(id, { status: 'active' });
                setEngagement(prev => ({ ...prev, status: 'active' }));
                toast({ message: 'Engagement reopened', type: 'success' });
              } catch (err) { toast({ message: err.message, type: 'error' }); }
            }} className="btn-secondary flex items-center gap-2 text-sm">
              <RotateCcw size={14} /> Reopen
            </button>
          )}
          {canEdit && engagement.status !== 'archived' && (
            <button onClick={async () => {
              const confirmed = window.confirm('Archive this engagement? It will be hidden from the active view.');
              if (!confirmed) return;
              try {
                await engApi.update(id, { status: 'archived' });
                setEngagement(prev => ({ ...prev, status: 'archived' }));
                toast({ message: 'Engagement archived', type: 'success' });
              } catch (err) { toast({ message: err.message, type: 'error' }); }
            }} className="btn-ghost text-sm themed-text-muted">
              Archive
            </button>
          )}
          {canEdit && engagement.status === 'archived' && (
            <button onClick={async () => {
              try {
                await engApi.update(id, { status: 'active' });
                setEngagement(prev => ({ ...prev, status: 'active' }));
                toast({ message: 'Engagement restored', type: 'success' });
              } catch (err) { toast({ message: err.message, type: 'error' }); }
            }} className="btn-secondary flex items-center gap-2 text-sm">
              <RotateCcw size={14} /> Restore
            </button>
          )}
          <button
            onClick={async () => {
              try {
                await exportImport.export(id);
                toast({ message: 'Engagement exported', type: 'success' });
              } catch (err) {
                toast({ message: err.message, type: 'error' });
              }
            }}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Share2 size={14} /> Export
          </button>
        </div>
      </div>

      {/* Severity summary */}
      <div className="flex items-center gap-4 mb-4">
        {Object.entries(sevCounts).map(([sev, count]) => (
          count > 0 && (
            <div key={sev} className="flex items-center gap-1.5">
              <SeverityBadge severity={sev} />
              <span className="text-sm font-mono themed-text-secondary">{count}</span>
            </div>
          )
        ))}
        {findingsList.length === 0 && <span className="text-sm themed-text-muted">No findings yet</span>}
      </div>

      {/* Local workspace search */}
      <WorkspaceSearch engId={id} onOpenTab={setActiveTab} toast={toast} />

      {/* Severity chart */}
      <SeverityChart findings={findingsList} />

      {/* Tabs */}
      <div className="flex mb-6 overflow-x-auto" style={{ borderBottom: '1px solid var(--border)' }}>
        <Tab active={activeTab === 'overview'} label="Overview" icon={LayoutDashboard}
          count={0} onClick={() => setActiveTab('overview')} />
        <Tab active={activeTab === 'findings'} label="Findings" icon={Target}
          count={findingsList.length} onClick={() => setActiveTab('findings')} />
        <Tab active={activeTab === 'retests'} label="Retests" icon={RotateCcw}
          count={activeRetestCount} onClick={() => setActiveTab('retests')} />
        <Tab active={activeTab === 'checklists'} label="Checklists" icon={ClipboardList}
          count={0} onClick={() => setActiveTab('checklists')} />
        <Tab active={activeTab === 'scans'} label="Scans" icon={Upload}
          count={0} onClick={() => setActiveTab('scans')} />
        <Tab active={activeTab === 'assets'} label="Assets" icon={Server}
          count={0} onClick={() => setActiveTab('assets')} />
        <Tab active={activeTab === 'notebook'} label="Notebook" icon={BookOpen}
          count={0} onClick={() => setActiveTab('notebook')} />
        <Tab active={activeTab === 'attack_paths'} label="Exploitation Chains" icon={Route}
          count={0} onClick={() => setActiveTab('attack_paths')} />
        <Tab active={activeTab === 'ad'} label="Active Directory" icon={Network}
          count={0} onClick={() => setActiveTab('ad')} />
        <Tab active={activeTab === 'gap_analysis'} label="Coverage Review" icon={ShieldAlert}
          count={0} onClick={() => setActiveTab('gap_analysis')} />
        <Tab active={activeTab === 'reports'} label="Reports" icon={FileText}
          count={0} onClick={() => setActiveTab('reports')} />
      </div>

      {activeTab === 'overview' && (
        <WorkspaceOverviewTab engId={id} findings={findingsList} toast={toast} onOpenTab={setActiveTab} />
      )}
      {activeTab === 'findings' && (
        <FindingsTab engId={id} findingsList={findingsList} setFindingsList={setFindingsList} toast={toast} />
      )}
      {activeTab === 'checklists' && (
        <ChecklistsTab engId={id} toast={toast} />
      )}
      {activeTab === 'scans' && (
        <ScansTab engId={id} toast={toast} onFindingsChanged={handleFindingsChanged} />
      )}
      {activeTab === 'retests' && (
        <RetestsTab engId={id} toast={toast} onFindingsChanged={handleFindingsChanged} onOpenFindings={() => setActiveTab('findings')} />
      )}
      {activeTab === 'assets' && (
        <AssetsTab engId={id} toast={toast} onOpenScans={() => setActiveTab('scans')} onOpenFindings={() => setActiveTab('findings')} onFindingsChanged={handleFindingsChanged} />
      )}
      {activeTab === 'notebook' && (
        <EvidenceNotebookTab engId={id} toast={toast} onFindingsChanged={handleFindingsChanged} onOpenFindings={() => setActiveTab('findings')} />
      )}
      {activeTab === 'attack_paths' && (
        <AttackPathsTab engId={id} toast={toast} fullNarrative={fullNarrative} setFullNarrative={setFullNarrative} />
      )}
      {activeTab === 'reports' && (
        <ReportsTab engId={id} toast={toast} />
      )}
      {activeTab === 'ad' && (
        <ADTab engId={id} toast={toast} onFindingsCreated={async () => {
          const f = await findingsApi.list(id);
          setFindingsList(f);
        }} />
      )}
      {activeTab === 'gap_analysis' && (
        <GapAnalysisTab engId={id} toast={toast} />
      )}

      {toastData && <Toast {...toastData} onDismiss={() => setToastData(null)} />}
    </div>
  );
}
