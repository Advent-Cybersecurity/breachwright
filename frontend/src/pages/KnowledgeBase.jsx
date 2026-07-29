import { useState, useEffect } from 'react';
import { SectionHeader, SeverityBadge, EmptyState, Toast, Spinner, Modal } from '../components/UI';
import { knowledge, engagements as engApi } from '../api';
import {
  Brain, TrendingUp, Search, Building2, ChevronRight,
  Database, BarChart3, Target, RefreshCw, Eye, Lightbulb, Layers,
} from 'lucide-react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const CATEGORY_COLORS = {
  network: '#3b82f6', web: '#8b5cf6', authentication: '#f59e0b',
  authorization: '#ef4444', cryptography: '#06b6d4', configuration: '#10b981',
  active_directory: '#ec4899', cloud: '#6366f1', wireless: '#14b8a6',
  social_engineering: '#f97316', physical: '#64748b', other: '#71717a',
};

const SEV_COLORS = { critical: '#dc2626', high: '#f97316', medium: '#eab308', low: '#3b82f6', info: '#71717a' };

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="card p-4 flex items-center gap-4">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
        style={{ backgroundColor: `${color}15`, border: `1px solid ${color}30` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <p className="text-2xl font-bold themed-text-primary">{value}</p>
        <p className="text-xs themed-text-muted font-mono uppercase tracking-wider">{label}</p>
      </div>
    </div>
  );
}

function CategoryTag({ category }) {
  const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.other;
  return (
    <span className="text-xs font-mono px-2 py-0.5 rounded"
      style={{ backgroundColor: `${color}15`, color, border: `1px solid ${color}30` }}>
      {category?.replace('_', ' ')}
    </span>
  );
}

function EntryRow({ entry, onClick }) {
  return (
    <div className="flex items-center gap-4 px-5 py-4 transition-colors cursor-pointer"
      style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 50%, transparent)' }}
      onClick={onClick}
      onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
      onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
        style={{ backgroundColor: 'var(--bg-600)' }}>
        <Target size={18} className="themed-text-muted" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2.5 mb-1">
          <span className="font-medium themed-text-primary truncate">{entry.canonical_title}</span>
          <SeverityBadge severity={entry.default_severity || 'info'} />
        </div>
        <div className="flex items-center gap-2">
          <CategoryTag category={entry.category} />
          {entry.cwe_id && <span className="text-xs themed-text-muted font-mono">{entry.cwe_id}</span>}
        </div>
      </div>
      <div className="shrink-0 text-right mr-2">
        <p className="text-lg font-bold themed-text-primary">{entry.occurrence_count}</p>
        <p className="text-[10px] themed-text-muted font-mono">OCCURRENCES</p>
      </div>
      <div className="shrink-0 text-right mr-2">
        <p className="text-lg font-bold themed-text-primary">{entry.unique_client_count}</p>
        <p className="text-[10px] themed-text-muted font-mono">CLIENTS</p>
      </div>
      <ChevronRight size={16} className="themed-text-muted shrink-0" />
    </div>
  );
}

function EntryDetail({ entry, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    knowledge.getEntry(entry.id).then(setDetail).catch(() => {}).finally(() => setLoading(false));
  }, [entry.id]);

  return (
    <Modal open={true} onClose={onClose} title={entry.canonical_title} wide>
      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : detail ? (
        <div className="space-y-5">
          <div className="flex items-center gap-3 flex-wrap">
            <SeverityBadge severity={detail.entry.default_severity || 'info'} />
            <CategoryTag category={detail.entry.category} />
            {detail.entry.default_cvss && (
              <span className="text-xs font-mono themed-text-secondary">CVSS: {detail.entry.default_cvss}</span>
            )}
            {detail.entry.cwe_id && (
              <span className="text-xs font-mono themed-text-secondary">{detail.entry.cwe_id}</span>
            )}
            {detail.entry.mitre_attack_id && (
              <span className="text-xs font-mono themed-text-secondary">MITRE: {detail.entry.mitre_attack_id}</span>
            )}
          </div>

          {detail.entry.description && (
            <div>
              <h4 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-2">Description</h4>
              <p className="text-sm themed-text-secondary leading-relaxed">{detail.entry.description}</p>
            </div>
          )}

          {detail.entry.remediation && (
            <div>
              <h4 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-2">Remediation</h4>
              <p className="text-sm themed-text-secondary leading-relaxed">{detail.entry.remediation}</p>
            </div>
          )}

          <div>
            <h4 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3">
              Seen In ({detail.occurrences.length} occurrence{detail.occurrences.length !== 1 ? 's' : ''})
            </h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {detail.occurrences.map((occ, i) => (
                <div key={i} className="flex items-center justify-between px-3 py-2 rounded-md text-sm"
                  style={{ backgroundColor: 'var(--bg-700)' }}>
                  <div className="flex items-center gap-2">
                    <Building2 size={14} className="themed-text-muted" />
                    <span className="themed-text-primary font-medium">{occ.client_name}</span>
                  </div>
                  <span className="text-xs themed-text-muted font-mono">
                    {occ.linked_at ? new Date(occ.linked_at).toLocaleDateString() : '—'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm themed-text-muted">Failed to load entry details.</p>
      )}
    </Modal>
  );
}

function RecommendationsPanel({ engagements }) {
  const [selectedEng, setSelectedEng] = useState('');
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadRecs = async () => {
    if (!selectedEng) return;
    setLoading(true);
    try {
      const data = await knowledge.recommendations(selectedEng);
      setRecs(data.recommendations || []);
    } catch { setRecs([]); }
    finally { setLoading(false); }
  };

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Lightbulb size={18} style={{ color: '#f59e0b' }} />
        <h3 className="text-sm font-semibold themed-text-primary uppercase tracking-wider">Recommendations</h3>
      </div>
      <p className="text-xs themed-text-muted mb-4">
        Select an engagement to see findings you should check for, based on similar past engagements.
      </p>
      <div className="flex gap-3 mb-4">
        <select className="input flex-1 text-sm" value={selectedEng}
          onChange={e => setSelectedEng(e.target.value)}>
          <option value="">Select engagement...</option>
          {engagements.map(e => (
            <option key={e.id} value={e.id}>{e.name} ({e.client_name})</option>
          ))}
        </select>
        <button className="btn-primary text-sm" onClick={loadRecs} disabled={!selectedEng || loading}>
          {loading ? <Spinner className="w-4 h-4" /> : 'Analyze'}
        </button>
      </div>

      {recs !== null && (
        recs.length === 0 ? (
          <p className="text-sm themed-text-muted py-4 text-center">
            No recommendations — this engagement's coverage looks thorough, or there aren't enough similar engagements yet.
          </p>
        ) : (
          <div className="space-y-2">
            {recs.map((rec, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 rounded-lg"
                style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium themed-text-primary">{rec.title}</span>
                    <SeverityBadge severity={rec.severity || 'info'} />
                  </div>
                  <p className="text-xs themed-text-muted">{rec.reason}</p>
                </div>
                <div className="text-right shrink-0 ml-4">
                  {rec.cvss && <p className="text-sm font-mono font-bold themed-text-primary">{rec.cvss}</p>}
                  <p className="text-[10px] themed-text-muted">CVSS</p>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

function ClientsPanel() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedClient, setSelectedClient] = useState(null);
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  useEffect(() => {
    knowledge.clients().then(setClients).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadProfile = async (clientName) => {
    setSelectedClient(clientName);
    setProfileLoading(true);
    try { setProfile(await knowledge.clientProfile(clientName)); }
    catch { setProfile(null); }
    finally { setProfileLoading(false); }
  };

  if (loading) return <div className="flex justify-center py-8"><Spinner /></div>;

  return (
    <div className="space-y-4">
      <div className="card overflow-hidden">
        {clients.length === 0 ? (
          <p className="p-5 text-sm themed-text-muted text-center">No client data yet. Index some engagements first.</p>
        ) : (
          clients.map((c, i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-3 cursor-pointer transition-colors"
              style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 50%, transparent)',
                backgroundColor: selectedClient === c.client_name ? 'color-mix(in srgb, var(--bg-700) 50%, transparent)' : 'transparent' }}
              onClick={() => loadProfile(c.client_name)}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
              onMouseLeave={e => { if (selectedClient !== c.client_name) e.currentTarget.style.backgroundColor = 'transparent'; }}>
              <Building2 size={18} className="themed-text-muted shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium themed-text-primary">{c.client_name}</span>
              </div>
              <span className="text-xs themed-text-muted font-mono">{c.engagement_count} eng</span>
              <span className="text-xs themed-text-muted font-mono">{c.unique_finding_types} types</span>
              <ChevronRight size={14} className="themed-text-muted" />
            </div>
          ))
        )}
      </div>

      {profileLoading && <div className="flex justify-center py-4"><Spinner /></div>}

      {profile && !profileLoading && (
        <div className="card p-5">
          <h3 className="text-base font-semibold themed-text-primary mb-4">{profile.client_name} — Risk Profile</h3>
          <div className="grid grid-cols-3 gap-4 mb-5">
            <div className="text-center p-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
              <p className="text-xl font-bold themed-text-primary">{profile.engagement_count}</p>
              <p className="text-[10px] font-mono themed-text-muted">ENGAGEMENTS</p>
            </div>
            <div className="text-center p-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
              <p className="text-xl font-bold themed-text-primary">{profile.unique_finding_types}</p>
              <p className="text-[10px] font-mono themed-text-muted">FINDING TYPES</p>
            </div>
            <div className="text-center p-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
              <p className="text-xl font-bold themed-text-primary">{profile.total_occurrences}</p>
              <p className="text-[10px] font-mono themed-text-muted">TOTAL FINDINGS</p>
            </div>
          </div>

          <h4 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3">Severity Breakdown</h4>
          <div className="flex gap-2 mb-5">
            {Object.entries(profile.severity_breakdown || {}).filter(([,v]) => v > 0).map(([sev, count]) => (
              <div key={sev} className="flex-1 text-center p-2 rounded"
                style={{ backgroundColor: `${SEV_COLORS[sev]}15`, border: `1px solid ${SEV_COLORS[sev]}30` }}>
                <p className="text-lg font-bold" style={{ color: SEV_COLORS[sev] }}>{count}</p>
                <p className="text-[10px] font-mono uppercase" style={{ color: SEV_COLORS[sev] }}>{sev}</p>
              </div>
            ))}
          </div>

          <h4 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3">Finding Types</h4>
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {profile.finding_types?.map((f, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-2 rounded text-sm"
                style={{ backgroundColor: 'var(--bg-700)' }}>
                <div className="flex items-center gap-2 min-w-0">
                  <SeverityBadge severity={f.severity || 'info'} />
                  <span className="themed-text-primary truncate">{f.title}</span>
                </div>
                <CategoryTag category={f.category} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function KnowledgeBase() {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [entries, setEntries] = useState([]);
  const [trending, setTrending] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [sevFilter, setSevFilter] = useState('');
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [indexing, setIndexing] = useState(false);
  const [toast, setToast] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, t, e] = await Promise.all([
        knowledge.stats(),
        knowledge.trending(),
        engApi.list().catch(() => []),
      ]);
      setStats(s);
      setTrending(t);
      setEngagements(e);
    } catch {}
    finally { setLoading(false); }
  };

  const loadEntries = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (catFilter) params.set('category', catFilter);
      if (sevFilter) params.set('severity', sevFilter);
      const data = await knowledge.list(params.toString());
      setEntries(data.entries || []);
    } catch {}
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (tab === 'browse') loadEntries(); }, [tab, search, catFilter, sevFilter]);

  const indexAll = async () => {
    setIndexing(true);
    try {
      const result = await knowledge.indexAll();
      setToast({ message: `Indexed ${result.indexed} findings from ${result.engagements} engagement(s)`, type: 'success' });
      load();
    } catch (e) { setToast({ message: e.message, type: 'error' }); }
    finally { setIndexing(false); }
  };

  // Chart data
  const catData = stats ? Object.entries(stats.by_category || {}).map(([name, value]) => ({
    name: name.replace('_', ' '), value, fill: CATEGORY_COLORS[name] || '#71717a',
  })) : [];
  const sevData = stats ? Object.entries(stats.by_severity || {}).filter(([,v]) => v > 0).map(([name, value]) => ({
    name, value, fill: SEV_COLORS[name] || '#71717a',
  })) : [];

  const tabs = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'browse', label: 'Browse', icon: Database },
    { id: 'clients', label: 'Clients', icon: Building2 },
    { id: 'recommendations', label: 'Recommendations', icon: Lightbulb },
  ];

  return (
    <>
      <SectionHeader
        title="Knowledge Base"
        description="Cross-engagement intelligence — track patterns, trends, and gaps across all your assessments"
        action={
          <button className="btn-primary flex items-center gap-2 text-sm" onClick={indexAll} disabled={indexing}>
            {indexing ? <Spinner className="w-4 h-4" /> : <RefreshCw size={15} />}
            {indexing ? 'Indexing...' : 'Reindex All'}
          </button>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg" style={{ backgroundColor: 'var(--bg-800)' }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
            style={{
              backgroundColor: tab === t.id ? 'var(--bg-600)' : 'transparent',
              color: tab === t.id ? 'var(--text-primary)' : 'var(--text-muted)',
            }}>
            <t.icon size={15} />
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : (
        <>
          {/* ── OVERVIEW ── */}
          {tab === 'overview' && stats && (
            <div className="space-y-6">
              <div className="grid grid-cols-4 gap-4">
                <StatCard icon={Layers} label="Finding Types" value={stats.total_finding_types} color="#3b82f6" />
                <StatCard icon={Target} label="Total Occurrences" value={stats.total_occurrences} color="#ef4444" />
                <StatCard icon={Building2} label="Clients" value={stats.unique_clients} color="#10b981" />
                <StatCard icon={Database} label="Engagements Indexed" value={stats.indexed_engagements} color="#8b5cf6" />
              </div>

              <div className="grid grid-cols-2 gap-6">
                {catData.length > 0 && (
                  <div className="card p-5">
                    <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-4">By Category</h3>
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie data={catData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
                          {catData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex flex-wrap gap-2 mt-3">
                      {catData.map((d, i) => (
                        <span key={i} className="text-[10px] font-mono flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: d.fill }} />
                          <span className="themed-text-muted">{d.name} ({d.value})</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {sevData.length > 0 && (
                  <div className="card p-5">
                    <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-4">By Severity</h3>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={sevData}>
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} allowDecimals={false} />
                        <Tooltip contentStyle={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }} />
                        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                          {sevData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              {trending.length > 0 && (
                <div className="card p-5">
                  <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-4">
                    <TrendingUp size={14} className="inline mr-2" />
                    Most Common Finding Types
                  </h3>
                  <div className="space-y-2">
                    {trending.slice(0, 10).map((t, i) => (
                      <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-md"
                        style={{ backgroundColor: 'var(--bg-700)' }}>
                        <span className="text-xs font-mono themed-text-muted w-5">{i + 1}</span>
                        <span className="flex-1 text-sm themed-text-primary">{t.canonical_title}</span>
                        <SeverityBadge severity={t.default_severity || 'info'} />
                        <span className="text-xs font-mono themed-text-secondary">{t.occurrence_count}×</span>
                        <span className="text-xs themed-text-muted">{t.unique_client_count} client{t.unique_client_count !== 1 ? 's' : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {stats.total_finding_types === 0 && (
                <EmptyState icon={Brain} title="No Data Yet"
                  description="Index your engagements to start building the knowledge base. Patterns and trends will appear as you add more data."
                  action={
                    <button className="btn-primary text-sm flex items-center gap-2" onClick={indexAll} disabled={indexing}>
                      <RefreshCw size={14} /> Index All Engagements
                    </button>
                  }
                />
              )}
            </div>
          )}

          {/* ── BROWSE ── */}
          {tab === 'browse' && (
            <div className="space-y-4">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
                  <input className="input pl-9 w-full text-sm" placeholder="Search finding types..."
                    value={search} onChange={e => setSearch(e.target.value)} />
                </div>
                <select className="input text-sm" value={catFilter} onChange={e => setCatFilter(e.target.value)}>
                  <option value="">All Categories</option>
                  {Object.keys(CATEGORY_COLORS).map(c => (
                    <option key={c} value={c}>{c.replace('_', ' ')}</option>
                  ))}
                </select>
                <select className="input text-sm" value={sevFilter} onChange={e => setSevFilter(e.target.value)}>
                  <option value="">All Severities</option>
                  {['critical', 'high', 'medium', 'low', 'info'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div className="card overflow-hidden">
                {entries.length === 0 ? (
                  <p className="p-8 text-sm themed-text-muted text-center">
                    {search || catFilter || sevFilter ? 'No entries match your filters.' : 'No entries in the knowledge base yet.'}
                  </p>
                ) : (
                  entries.map(e => (
                    <EntryRow key={e.id} entry={e} onClick={() => setSelectedEntry(e)} />
                  ))
                )}
              </div>
            </div>
          )}

          {/* ── CLIENTS ── */}
          {tab === 'clients' && <ClientsPanel />}

          {/* ── RECOMMENDATIONS ── */}
          {tab === 'recommendations' && <RecommendationsPanel engagements={engagements} />}
        </>
      )}

      {selectedEntry && <EntryDetail entry={selectedEntry} onClose={() => setSelectedEntry(null)} />}
      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </>
  );
}
