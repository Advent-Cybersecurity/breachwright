import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import {
  engagements as engApi, findings as findingsApi, analysis as analysisApi,
  attackPaths as apApi, reports as reportsApi, evidence as evidenceApi,
  narratives as narrativeApi,
  exportImport, ad as adApi, reportTemplates as templatesApi
} from '../api';
import { Modal, SeverityBadge, StatusBadge, EmptyState, SectionHeader, Toast, Spinner } from '../components/UI';
import ADPathGraph from '../components/ADPathGraph';
import ChecklistsTab from '../components/ChecklistsTab';
import GapAnalysisTab from '../components/GapAnalysisTab';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  ArrowLeft, Plus, Upload, Zap, Route, FileText, Trash2, Download,
  Search, AlertTriangle, Target, ChevronDown, ChevronRight, ExternalLink,
  Brain, Crosshair, Shield, Edit3, Check, RotateCcw, Image, Paperclip,
  Share2, Network, Users, ClipboardList, Palette, ShieldAlert, BookOpen
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
        <div className="flex-1 h-40">
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
function FindingForm({ form, setForm, onSubmit, saving, submitLabel }) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label htmlFor="finding-title" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Title</label>
        <input id="finding-title" className="input-field text-sm" value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })} required autoFocus />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label htmlFor="finding-severity" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Severity</label>
          <select id="finding-severity" className="input-field text-sm" value={form.severity}
            onChange={(e) => setForm({ ...form, severity: e.target.value })}>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>
        </div>
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
    affected_hosts: '', evidence: '', remediation: '', retest_status: null
  });
  const [saving, setSaving] = useState(false);

  const resetForm = () => setForm({
    title: '', description: '', severity: 'medium', cvss_score: '',
    affected_hosts: '', evidence: '', remediation: '', retest_status: null
  });

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
    });
    setEditFinding(finding);
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const finding = await findingsApi.create(engId, {
        ...form,
        cvss_score: form.cvss_score ? parseFloat(form.cvss_score) : null,
      });
      setFindingsList(prev => [...prev, finding]);
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
    if (selected.size === findingsList.length) setSelected(new Set());
    else setSelected(new Set(findingsList.map(f => f.id)));
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
            <button onClick={() => { resetForm(); setShowAdd(true); }} className="btn-primary flex items-center gap-2">
              <Plus size={16} /> Add Finding
            </button>
          }
        />
      ) : (
        <>
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
            <button onClick={() => { resetForm(); setShowAdd(true); }} className="btn-secondary flex items-center gap-2 text-sm">
              <Plus size={14} /> Add Finding
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs font-mono themed-text-muted uppercase tracking-wider"
                  style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className="py-3 px-2 w-8">
                    <input type="checkbox" checked={selected.size === findingsList.length && findingsList.length > 0}
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
                {findingsList.map(f => (
                  <FindingRow key={f.id} finding={f} engId={engId}
                    selected={selected.has(f.id)}
                    onToggleSelect={() => toggleSelect(f.id)}
                    onEdit={() => openEdit(f)}
                    onDelete={() => handleDelete(f.id)}
                    toast={toast} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Add modal */}
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Finding" wide>
        <FindingForm form={form} setForm={setForm} onSubmit={handleAdd} saving={saving} submitLabel="Save Finding" />
      </Modal>

      {/* Edit modal */}
      <Modal open={!!editFinding} onClose={() => setEditFinding(null)} title="Edit Finding" wide>
        <FindingForm form={form} setForm={setForm} onSubmit={handleEdit} saving={saving} submitLabel="Update Finding" />
      </Modal>
    </div>
  );
}

// Finding row with evidence support
function FindingRow({ finding, engId, selected, onToggleSelect, onEdit, onDelete, toast }) {
  const [expanded, setExpanded] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
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
      setAttachments(await Promise.all(data.map(withObjectUrl)));
    } catch (e) {}
    finally { setLoadingEvidence(false); }
  };

  const handleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) loadEvidence();
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
        <td className="py-3 px-4 font-mono themed-text-secondary">{finding.cvss_score || '-'}</td>
        <td className="py-3 px-4 themed-text-secondary text-xs font-mono truncate max-w-[200px]">
          {finding.affected_hosts || '-'}
        </td>
        <td className="py-3 px-4">
          <RetestBadge status={finding.retest_status} />
        </td>
        <td className="py-3 px-4">
          <span className={`text-xs font-mono ${finding.source === 'ai_generated' ? 'text-cyan-400' : 'themed-text-muted'}`}>
            {finding.source === 'ai_generated' ? 'AI' : 'Manual'}
          </span>
        </td>
        <td className="py-3 px-4">
          <div className="flex items-center gap-1">
            <button onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="themed-text-muted hover:text-blue-400 transition-colors p-1" title="Edit">
              <Edit3 size={14} />
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
          <td colSpan={7} className="px-4 py-4">
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
              {finding.remediation && (
                <div>
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider block mb-1">Remediation</span>
                  <p className="themed-text-secondary whitespace-pre-wrap">{finding.remediation}</p>
                </div>
              )}
              {/* Evidence Attachments */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider flex items-center gap-1.5">
                    <Paperclip size={12} /> Evidence Attachments
                    {attachments.length > 0 && ` (${attachments.length})`}
                  </span>
                  <label className="btn-ghost flex items-center gap-1 text-xs cursor-pointer">
                    <Image size={12} /> Attach
                    <input type="file" className="hidden" accept="image/*,.pdf" onChange={handleUploadEvidence} />
                  </label>
                </div>
                {loadingEvidence && <Spinner className="w-4 h-4 themed-text-muted" />}
                {attachments.length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {attachments.map(att => (
                      <div key={att.id} className="relative group rounded overflow-hidden"
                        style={{ backgroundColor: 'var(--bg-800)', border: '1px solid var(--border)' }}>
                        {att.content_type?.startsWith('image/') ? (
                          <a href={att.objectUrl} target="_blank" rel="noopener noreferrer">
                            <img src={att.objectUrl} alt={att.filename}
                              className="w-full h-32 object-cover cursor-pointer hover:opacity-80 transition-opacity" />
                          </a>
                        ) : (
                          <a href={att.objectUrl} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-2 p-3 text-xs themed-text-secondary hover:themed-text-primary">
                            <FileText size={14} /> {att.filename}
                          </a>
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

// Scans tab
function ScansTab({ engId, toast, onAnalysisComplete }) {
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [scans, setScans] = useState([]);
  const [scanType, setScanType] = useState('nmap');
  const [loadingScans, setLoadingScans] = useState(true);

  useEffect(() => {
    analysisApi.listScans(engId)
      .then(setScans)
      .catch(() => {})
      .finally(() => setLoadingScans(false));
  }, [engId]);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const scan = await analysisApi.uploadScan(engId, file, scanType);
      setScans(prev => [...prev, scan]);
      toast({ message: `Uploaded ${scan.filename}`, type: 'success' });
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
      const results = await analysisApi.run(engId);
      toast({ message: `Analysis generated ${results.length} findings`, type: 'success' });
      onAnalysisComplete(results);
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card p-6" style={{ borderStyle: 'dashed' }}>
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="flex-1">
            <h3 className="text-sm font-semibold themed-text-primary mb-1">Upload Scan Data</h3>
            <p className="text-xs themed-text-muted">Nmap XML, Nessus .nessus, Burp XML, or raw text output.</p>
          </div>
          <div className="flex items-center gap-3">
            <select className="input-field text-sm w-28" value={scanType}
              onChange={(e) => setScanType(e.target.value)}>
              <option value="nmap">Nmap</option>
              <option value="nessus">Nessus</option>
              <option value="burp">Burp</option>
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
            <div className="space-y-2">
              {scans.map(s => (
                <div key={s.id} className="flex items-center gap-3 text-sm">
                  <FileText size={14} className="themed-text-muted" />
                  <span className="font-mono themed-text-secondary flex-1">{s.filename}</span>
                  <span className="badge" style={{ backgroundColor: 'var(--bg-600)', color: 'var(--text-muted)' }}>
                    {s.scan_type}
                  </span>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await analysisApi.deleteScan(engId, s.id);
                        setScans(prev => prev.filter(x => x.id !== s.id));
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
            </div>
          </div>
        )}
      </div>

      <div className="card p-6">
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Brain size={16} className="text-cyan-400" />
              <h3 className="text-sm font-semibold themed-text-primary">AI Analysis</h3>
            </div>
            <p className="text-xs themed-text-muted">
              Analyze uploaded scans and generate findings with severity ratings, CVSS scores, and remediation guidance.
            </p>
          </div>
          <button onClick={handleAnalyze} disabled={analyzing || scans.length === 0}
            className="btn-primary flex items-center gap-2 whitespace-nowrap">
            {analyzing ? <Spinner className="w-4 h-4" /> : <Zap size={16} />}
            {analyzing ? 'Analyzing...' : 'Run Analysis'}
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
    }).catch(() => {}).finally(() => setLoading(false));
    // Load saved full narrative
    if (!fullNarrative) {
      narrativeApi.getSaved(engId).then(saved => {
        if (saved) setFullNarrative(saved);
      }).catch(() => {});
    }
  }, [engId]);

  const handleGenerate = async () => {
    if (paths.length > 0) {
      const confirmed = window.confirm(
        `This will replace the existing ${paths.length} exploitation chain(s) with a fresh analysis based on current findings. Continue?`
      );
      if (!confirmed) return;
    }
    setGenerating(true);
    setFullNarrative(null);
    narrativeApi.deleteFull(engId).catch(() => {});
    try {
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
                setPaths([]);
                setFullNarrative(null);
                narrativeApi.deleteFull(engId).catch(() => {});
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
                setFullNarrative(result);
                // Save to DB for persistence
                narrativeApi.saveFull(engId, result).catch(() => {});
                toast({ message: 'Attack narrative generated', type: 'success' });
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
        setFullNarrative(null);
        narrativeApi.deleteFull(engId).catch(() => {});
        toast({ message: 'Narrative deleted', type: 'success' });
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

  useEffect(() => {
    (async () => {
      try {
        const [reports, tmpls] = await Promise.all([
          reportsApi.list(engId),
          templatesApi.list(),
        ]);
        setReportList(reports);
        setTemplates(tmpls);
        const def = tmpls.find(t => t.is_default);
        if (def) setSelectedTemplate(def.id);
      } catch (e) {}
      finally { setLoading(false); }
    })();
  }, [engId]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const templateId = reportFormat === 'docx' && selectedTemplate ? selectedTemplate : null;
      const report = await reportsApi.generate(engId, reportFormat, templateId, useAI);
      setReportList(prev => [report, ...prev]);
      const tName = templates.find(t => t.id === selectedTemplate)?.name;
      toast({ message: `${reportFormat.toUpperCase()} report generated${useAI ? ' with AI enhancement' : ' locally'}${tName ? ` with "${tName}" template` : ''}`, type: 'success' });
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

  return (
    <div>
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
                <button onClick={() => startEditTemplate(t)} className="themed-text-muted hover:text-white transition-colors p-1"><Edit3 size={12} /></button>
                <button onClick={() => handleDeleteTemplate(t.id)} className="themed-text-muted hover:text-red-400 transition-colors p-1"><Trash2 size={12} /></button>
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
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Template Name *</label>
                <input className="input-field text-sm" value={templateForm.name} onChange={e => setTemplateForm(p => ({ ...p, name: e.target.value }))} placeholder="Client Report Template" />
              </div>
              <div>
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Company Name</label>
                <input className="input-field text-sm" value={templateForm.company_name} onChange={e => setTemplateForm(p => ({ ...p, company_name: e.target.value }))} placeholder="Acme Security Inc." />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Primary Color</label>
                <div className="flex items-center gap-2">
                  <input type="color" value={templateForm.primary_color} onChange={e => setTemplateForm(p => ({ ...p, primary_color: e.target.value }))} className="w-8 h-8 rounded cursor-pointer" style={{ border: 'none', padding: 0 }} />
                  <input className="input-field text-sm font-mono flex-1" value={templateForm.primary_color} onChange={e => setTemplateForm(p => ({ ...p, primary_color: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Logo</label>
                <label className="btn-secondary text-xs cursor-pointer inline-flex items-center gap-1">
                  <Upload size={12} /> {logoFile ? logoFile.name : editingTemplate?.has_logo ? 'Replace Logo' : 'Upload Logo'}
                  <input type="file" className="hidden" accept=".png,.jpg,.jpeg" onChange={e => setLogoFile(e.target.files[0])} />
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Report Header</label>
                <input className="input-field text-sm" value={templateForm.header_text} onChange={e => setTemplateForm(p => ({ ...p, header_text: e.target.value }))} placeholder="PENETRATION TEST REPORT" />
              </div>
              <div>
                <label className="block text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Report Footer</label>
                <input className="input-field text-sm" value={templateForm.footer_text} onChange={e => setTemplateForm(p => ({ ...p, footer_text: e.target.value }))} placeholder="CONFIDENTIAL" />
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
          <select className="input-field text-sm" style={{ maxWidth: 200 }} value={selectedTemplate}
            onChange={e => setSelectedTemplate(e.target.value)}>
            <option value="">Default Branding</option>
            {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        )}
        <select className="input-field text-sm w-28" value={reportFormat}
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
                  {report.created_at && ` // ${new Date(report.created_at).toLocaleString()}`}
                </p>
              </div>
              <button
                onClick={async () => {
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
      } catch (e) {}
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
      setPaths(result);
      toast({ message: `Identified ${result.length} AD attack paths (findings added to Findings tab)`, type: 'success' });
      if (onFindingsCreated) await onFindingsCreated();
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
  const { user } = useAuth();
  const canEdit = user?.role !== 'viewer';
  const { id } = useParams();
  const navigate = useNavigate();
  const [engagement, setEngagement] = useState(null);
  const [findingsList, setFindingsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('findings');
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

  const handleAnalysisComplete = (newFindings) => {
    setFindingsList(prev => [...prev, ...newFindings]);
    setActiveTab('findings');
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Spinner className="w-6 h-6" style={{ color: 'var(--accent-red)' }} /></div>;
  }

  if (!engagement) {
    return <div className="text-center py-20 themed-text-muted">Engagement not found.</div>;
  }

  const sevCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  findingsList.forEach(f => { sevCounts[f.severity] = (sevCounts[f.severity] || 0) + 1; });

  return (
    <div className="animate-fade-in">
      <button onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-sm themed-text-muted transition-colors mb-5"
        onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}>
        <ArrowLeft size={16} /> Back to Engagements
      </button>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
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
        <div className="flex items-center gap-2 self-start">
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

      {!canEdit && (
        <div
          className="mb-5 px-4 py-3 rounded-lg text-sm themed-text-secondary"
          style={{
            backgroundColor: 'rgba(59,130,246,0.08)',
            border: '1px solid rgba(59,130,246,0.2)',
          }}
        >
          Read-only access: you can review and export this engagement. Changes,
          tool execution, uploads, and AI-assisted actions are disabled for
          viewer accounts.
        </div>
      )}

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

      {/* Severity chart */}
      <SeverityChart findings={findingsList} />

      {/* Tabs */}
      <div className="flex mb-6" style={{ borderBottom: '1px solid var(--border)' }}>
        <Tab active={activeTab === 'findings'} label="Findings" icon={Target}
          count={findingsList.length} onClick={() => setActiveTab('findings')} />
        <Tab active={activeTab === 'checklists'} label="Checklists" icon={ClipboardList}
          count={0} onClick={() => setActiveTab('checklists')} />
        <Tab active={activeTab === 'scans'} label="Scans" icon={Upload}
          count={0} onClick={() => setActiveTab('scans')} />
        <Tab active={activeTab === 'attack_paths'} label="Exploitation Chains" icon={Route}
          count={0} onClick={() => setActiveTab('attack_paths')} />
        <Tab active={activeTab === 'ad'} label="Active Directory" icon={Network}
          count={0} onClick={() => setActiveTab('ad')} />
        <Tab active={activeTab === 'gap_analysis'} label="Coverage Review" icon={ShieldAlert}
          count={0} onClick={() => setActiveTab('gap_analysis')} />
        <Tab active={activeTab === 'reports'} label="Reports" icon={FileText}
          count={0} onClick={() => setActiveTab('reports')} />
      </div>

      {activeTab === 'findings' && (
        <FindingsTab engId={id} findingsList={findingsList} setFindingsList={setFindingsList} toast={toast} />
      )}
      {activeTab === 'checklists' && (
        <ChecklistsTab engId={id} toast={toast} />
      )}
      {activeTab === 'scans' && (
        <ScansTab engId={id} toast={toast} onAnalysisComplete={handleAnalysisComplete} />
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
