import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { engagements as engApi, exportImport } from '../api';
import { Modal, StatusBadge, SeverityBadge, EmptyState, SectionHeader, Toast } from '../components/UI';
import { Plus, Search, Crosshair, ChevronRight, FolderOpen, Calendar, Building2, Upload, Trash2, BarChart3 } from 'lucide-react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

function EngagementRow({ engagement, onClick, onDelete }) {
  return (
    <div className="flex items-center gap-4 px-5 py-4 transition-colors"
      style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}
      onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
      onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
      <button onClick={onClick} className="flex items-center gap-4 flex-1 min-w-0 text-left">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 transition-colors"
          style={{ backgroundColor: 'var(--bg-600)' }}>
          <Crosshair size={18} className="themed-text-muted" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 mb-0.5">
            <span className="font-medium themed-text-primary truncate">{engagement.name}</span>
            <StatusBadge status={engagement.status} />
          </div>
          <div className="flex items-center gap-3 text-xs themed-text-muted">
            <span className="flex items-center gap-1"><Building2 size={12} />{engagement.client_name}</span>
            {engagement.start_date && <span className="flex items-center gap-1"><Calendar size={12} />{engagement.start_date}</span>}
          </div>
        </div>
        <div className="shrink-0 text-right mr-2">
          <span className="text-xs themed-text-secondary font-mono">{engagement.finding_count} finding{engagement.finding_count !== 1 ? 's' : ''}</span>
        </div>
        <ChevronRight size={16} className="themed-text-muted shrink-0" />
      </button>
      {onDelete && (
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="themed-text-muted hover:text-red-400 transition-colors p-2 shrink-0" title="Delete engagement">
          <Trash2 size={15} />
        </button>
      )}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const canEdit = true;
  const [engagementList, setEngagementList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [toast, setToast] = useState(null);
  const [form, setForm] = useState({ name: '', client_name: '', scope: '', start_date: '', end_date: '', template_key: '' });
  const [creating, setCreating] = useState(false);
  const [analytics, setAnalytics] = useState(null);

  const loadEngagements = async () => {
    try { setEngagementList(await engApi.list()); }
    catch (err) { setToast({ message: err.message, type: 'error' }); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    loadEngagements();
    engApi.analytics().then(setAnalytics).catch(() => {});
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const eng = await engApi.create({ ...form, start_date: form.start_date || null, end_date: form.end_date || null, template_key: form.template_key || null });
      setShowCreate(false);
      setForm({ name: '', client_name: '', scope: '', start_date: '', end_date: '', template_key: '' });
      setToast({ message: `Engagement "${eng.name}" created`, type: 'success' });
      await loadEngagements();
      navigate(`/engagements/${eng.id}`);
    } catch (err) { setToast({ message: err.message, type: 'error' }); }
    finally { setCreating(false); }
  };

  const filtered = engagementList.filter(e => {
    const matchSearch = e.name.toLowerCase().includes(search.toLowerCase()) ||
      e.client_name.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'all' || e.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const stats = {
    total: engagementList.length,
    active: engagementList.filter(e => e.status === 'active').length,
    completed: engagementList.filter(e => e.status === 'completed').length,
    archived: engagementList.filter(e => e.status === 'archived').length,
    totalFindings: engagementList.reduce((sum, e) => sum + (e.finding_count || 0), 0),
  };

  return (
    <div className="animate-fade-in">
      <SectionHeader
        title="Engagements"
        description={`${stats.total} total, ${stats.active} active, ${stats.completed} completed, ${stats.totalFindings} findings`}
        action={canEdit ? (
          <div className="flex items-center gap-2">
            <label className="btn-secondary flex items-center gap-2 cursor-pointer">
              <Upload size={16} /> Import
              <input type="file" className="hidden" accept=".json"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (!file) return;
                  try {
                    const result = await exportImport.import(file);
                    const details = [
                      `${result.findings_imported} findings`,
                      `${result.checklist_items_imported || 0} checklist items`,
                      `${result.scan_snapshots_imported || 0} scan snapshots`,
                    ].join(', ');
                    setToast({ message: `Imported "${result.name}" with ${details}`, type: 'success' });
                    await loadEngagements();
                    navigate(`/engagements/${result.id}`);
                  } catch (err) {
                    setToast({ message: err.message, type: 'error' });
                  }
                  e.target.value = '';
                }}
              />
            </label>
            <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-2">
              <Plus size={16} /> New Engagement
            </button>
          </div>
        ) : null}
      />

      {/* Analytics */}
      {analytics && analytics.total_findings > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="card p-4">
            <div className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3">Severity Breakdown</div>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={[
                  { name: 'Critical', value: analytics.severity_distribution.critical || 0 },
                  { name: 'High', value: analytics.severity_distribution.high || 0 },
                  { name: 'Medium', value: analytics.severity_distribution.medium || 0 },
                  { name: 'Low', value: analytics.severity_distribution.low || 0 },
                  { name: 'Info', value: analytics.severity_distribution.info || 0 },
                ].filter(d => d.value > 0)} dataKey="value" cx="50%" cy="50%" innerRadius={40} outerRadius={65}>
                  {['#ef4444','#f97316','#eab308','#3b82f6','#6b7280'].map((c,i) => <Cell key={i} fill={c} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="card p-4">
            <div className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3">Findings by Engagement</div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={analytics.per_engagement}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                <Tooltip />
                <Bar dataKey="findings" fill="#ef4444" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {engagementList.length > 0 && (
        <div className="flex items-center gap-2 mb-4">
          {[
            { key: 'all', label: 'All', count: stats.total },
            { key: 'active', label: 'Active', count: stats.active },
            { key: 'completed', label: 'Completed', count: stats.completed },
            { key: 'archived', label: 'Archived', count: stats.archived },
          ].map(f => (
            <button key={f.key} onClick={() => setStatusFilter(f.key)}
              className="text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
              style={{
                backgroundColor: statusFilter === f.key ? 'rgba(239,68,68,0.15)' : 'var(--bg-700)',
                color: statusFilter === f.key ? 'var(--accent-red)' : 'var(--text-muted)',
                border: `1px solid ${statusFilter === f.key ? 'rgba(239,68,68,0.3)' : 'var(--bg-500)'}`,
              }}>
              {f.label} {f.count > 0 && <span className="font-mono ml-1">{f.count}</span>}
            </button>
          ))}
        </div>
      )}

      {engagementList.length > 0 && (
        <div className="relative mb-5">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
            className="input-field pl-9 text-sm" placeholder="Search engagements..." />
        </div>
      )}

      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--accent-red)', borderTopColor: 'transparent' }} />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState icon={FolderOpen}
            title={search ? 'No matches' : 'No engagements yet'}
            description={search
              ? 'Try a different search term.'
              : canEdit
                ? 'Create your first engagement to get started.'
                : 'No engagement data is available to view.'}
            action={!search && canEdit && (
              <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-2">
                <Plus size={16} /> New Engagement
              </button>
            )}
          />
        ) : filtered.map(eng => (
          <EngagementRow key={eng.id} engagement={eng}
            onClick={() => navigate(`/engagements/${eng.id}`)}
            onDelete={canEdit ? async () => {
              const confirmed = window.confirm(`Delete engagement "${eng.name}" and all its data? This cannot be undone.`);
              if (!confirmed) return;
              try {
                await engApi.delete(eng.id);
                setEngagementList(prev => prev.filter(e => e.id !== eng.id));
                setToast({ message: `Engagement "${eng.name}" deleted`, type: 'success' });
              } catch (err) {
                setToast({ message: err.message, type: 'error' });
              }
            } : null}
          />
        ))}
      </div>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New Engagement">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label htmlFor="engagement-name" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Name</label>
            <input id="engagement-name" className="input-field text-sm" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="External Pentest Q1 2026" required autoFocus />
          </div>
          <div>
            <label htmlFor="engagement-client" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Client</label>
            <input id="engagement-client" className="input-field text-sm" value={form.client_name}
              onChange={(e) => setForm({ ...form, client_name: e.target.value })}
              placeholder="Acme Corp" required />
          </div>
          <div>
            <label htmlFor="engagement-scope" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Scope</label>
            <textarea id="engagement-scope" className="input-field text-sm resize-none" rows={3} value={form.scope}
              onChange={(e) => setForm({ ...form, scope: e.target.value })}
              placeholder="10.10.10.0/24, *.example.com" />
          </div>
          <div>
            <label htmlFor="engagement-template" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Assessment Template</label>
            <select id="engagement-template" className="input-field text-sm" value={form.template_key}
              onChange={(e) => setForm({ ...form, template_key: e.target.value })}>
              <option value="">Blank engagement</option>
              <option value="web">Web Application</option>
              <option value="api">API Security</option>
              <option value="external">External Network</option>
              <option value="internal">Internal Network</option>
              <option value="active_directory">Active Directory</option>
              <option value="cloud">Cloud Environment</option>
            </select>
            <p className="text-xs themed-text-muted mt-1">Templates automatically add the most relevant built-in methodology checklist.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="engagement-start" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Start</label>
              <input id="engagement-start" type="date" className="input-field text-sm" value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div>
              <label htmlFor="engagement-end" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">End</label>
              <input id="engagement-end" type="date" className="input-field text-sm" value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={creating} className="btn-primary flex items-center gap-2">
              {creating && <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
              Create
            </button>
          </div>
        </form>
      </Modal>

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
