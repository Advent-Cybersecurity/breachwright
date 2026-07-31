import { useEffect, useState } from 'react';
import { gapAnalysis } from '../api';
import { SeverityBadge, Spinner } from './UI';
import {
  ShieldAlert, CheckCircle2, XCircle, AlertTriangle, ChevronDown,
  ChevronRight, Play, ExternalLink, Gauge,
} from 'lucide-react';

const GAP_TYPE_STYLES = {
  not_tested: { bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.25)', icon: XCircle, color: '#ef4444', label: 'Not Tested' },
  undertested: { bg: 'rgba(234,179,8,0.1)', border: 'rgba(234,179,8,0.25)', icon: AlertTriangle, color: '#eab308', label: 'Undertested' },
};

function CoverageGauge({ score }) {
  const color = score >= 80 ? '#10b981' : score >= 50 ? '#eab308' : '#ef4444';
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative w-36 h-36 flex items-center justify-center">
      <svg width="136" height="136" className="transform -rotate-90">
        <circle cx="68" cy="68" r={radius} fill="none" stroke="var(--bg-600)" strokeWidth="10" />
        <circle cx="68" cy="68" r={radius} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" className="transition-all duration-1000" />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-3xl font-bold" style={{ color }}>{score}</span>
        <span className="text-[10px] font-mono themed-text-muted uppercase">Coverage</span>
      </div>
    </div>
  );
}

function GapCard({ gap, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const style = GAP_TYPE_STYLES[gap.type] || GAP_TYPE_STYLES.not_tested;
  const Icon = style.icon;

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${style.border}`, backgroundColor: style.bg }}>
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <Icon size={18} style={{ color: style.color }} className="shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-medium themed-text-primary">{gap.item}</span>
            <SeverityBadge severity={gap.severity} />
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{ backgroundColor: `${style.color}20`, color: style.color }}>
              {style.label}
            </span>
          </div>
          <span className="text-xs themed-text-muted">{gap.category}</span>
        </div>
        {open ? <ChevronDown size={16} className="themed-text-muted shrink-0" /> :
          <ChevronRight size={16} className="themed-text-muted shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3" style={{ borderTop: `1px solid ${style.border}` }}>
          <div className="pt-3">
            <h4 className="text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Why This Is a Gap</h4>
            <p className="text-sm themed-text-secondary">{gap.reason}</p>
          </div>
          <div>
            <h4 className="text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Recommendation</h4>
            <p className="text-sm themed-text-secondary">{gap.recommendation}</p>
          </div>
          {gap.methodology_ref && (
            <div className="flex items-center gap-1 text-xs themed-text-muted">
              <ExternalLink size={12} />
              <span>{gap.methodology_ref}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OutOfScopeSection({ items }) {
  const [open, setOpen] = useState(false);
  if (!items || items.length === 0) return null;

  return (
    <div className="card p-4">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left">
        <CheckCircle2 size={16} style={{ color: '#10b981' }} />
        <span className="text-sm font-medium themed-text-primary flex-1">
          {items.length} Item{items.length !== 1 ? 's' : ''} Correctly Excluded (Out of Scope)
        </span>
        {open ? <ChevronDown size={14} className="themed-text-muted" /> :
          <ChevronRight size={14} className="themed-text-muted" />}
      </button>

      {open && (
        <div className="mt-3 space-y-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start gap-3 px-3 py-2 rounded-md"
              style={{ backgroundColor: 'var(--bg-700)' }}>
              <CheckCircle2 size={14} style={{ color: '#10b981' }} className="shrink-0 mt-0.5" />
              <div>
                <span className="text-sm themed-text-primary">{item.category} — {item.item}</span>
                <p className="text-xs themed-text-muted mt-0.5">{item.reason}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GapAnalysisTab({ engId, toast }) {
  const [methodology, setMethodology] = useState('network_pentest');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [methodologies, setMethodologies] = useState(null);

  const runAnalysis = async () => {
    setLoading(true);
    setResult(null);
    try {
      const data = await gapAnalysis.run(engId, methodology);
      setResult(data);
    } catch (e) {
      toast({ message: e.message, type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    gapAnalysis.methodologies(engId)
      .then(data => {
        if (!cancelled) setMethodologies(data);
      })
      .catch(error => {
        if (!cancelled) toast({ message: `Could not load coverage methods: ${error.message}`, type: 'error' });
      });
    return () => { cancelled = true; };
  }, [engId, toast]);

  const gaps = result?.gaps || [];
  const highGaps = gaps.filter(g => g.severity === 'high');
  const medGaps = gaps.filter(g => g.severity === 'medium');
  const lowGaps = gaps.filter(g => g.severity === 'low');

  return (
    <div className="space-y-6">
        {/* Controls */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={18} style={{ color: 'var(--accent-red)' }} />
            <h3 className="text-sm font-semibold themed-text-primary uppercase tracking-wider">
              Coverage Review
            </h3>
          </div>
          <p className="text-sm themed-text-muted mb-4">
            AI reviews your findings, scans, and checklist progress against the selected methodology.
            It understands your scope and only flags gaps that are relevant.
          </p>

          <div className="flex gap-3">
            <select className="input flex-1 text-sm" value={methodology}
              onChange={e => setMethodology(e.target.value)}>
              {methodologies ? (
                Object.entries(methodologies).map(([key, m]) => (
                  <option key={key} value={key}>{m.name} ({m.item_count} items)</option>
                ))
              ) : (
                <>
                  <option value="network_pentest">Network Penetration Test</option>
                  <option value="ptes">PTES</option>
                  <option value="owasp_top10">OWASP Top 10</option>
                  <option value="nist_800_115">NIST SP 800-115</option>
                </>
              )}
            </select>
            <button className="btn-primary flex items-center gap-2 text-sm" onClick={runAnalysis}
              disabled={loading}>
              {loading ? <Spinner className="w-4 h-4" /> : <Play size={15} />}
              {loading ? 'Analyzing...' : 'Review Coverage'}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-12">
            <Spinner className="w-8 h-8 mb-3" style={{ color: 'var(--accent-red)' }} />
            <p className="text-sm themed-text-muted">AI is reviewing your engagement against {methodology.replace(/_/g, ' ')}...</p>
            <p className="text-xs themed-text-muted mt-1">This may take 15-30 seconds</p>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-6">
            {/* Summary bar */}
            <div className="card p-5">
              <div className="flex items-center gap-8">
                <CoverageGauge score={result.coverage_score || 0} />

                <div className="flex-1 space-y-3">
                  <div>
                    <h3 className="text-base font-semibold themed-text-primary mb-1">
                      {result.methodology_name}
                    </h3>
                    {result.engagement_type && (
                      <div className="flex gap-2 flex-wrap mb-2">
                        {result.engagement_type.map(t => (
                          <span key={t} className="text-[10px] font-mono px-2 py-0.5 rounded"
                            style={{ backgroundColor: 'rgba(99,102,241,0.15)', color: '#818cf8',
                              border: '1px solid rgba(99,102,241,0.3)' }}>
                            {t.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="text-sm themed-text-secondary">{result.summary}</p>
                  </div>

                  <div className="flex gap-4">
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold themed-text-primary">{result.finding_count}</p>
                      <p className="text-[10px] font-mono themed-text-muted">FINDINGS</p>
                    </div>
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold themed-text-primary">{result.gap_count}</p>
                      <p className="text-[10px] font-mono themed-text-muted">GAPS</p>
                    </div>
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold" style={{ color: '#ef4444' }}>
                        {result.gap_severity_breakdown?.high || 0}
                      </p>
                      <p className="text-[10px] font-mono themed-text-muted">HIGH</p>
                    </div>
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold" style={{ color: '#eab308' }}>
                        {result.gap_severity_breakdown?.medium || 0}
                      </p>
                      <p className="text-[10px] font-mono themed-text-muted">MEDIUM</p>
                    </div>
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold" style={{ color: '#3b82f6' }}>
                        {result.gap_severity_breakdown?.low || 0}
                      </p>
                      <p className="text-[10px] font-mono themed-text-muted">LOW</p>
                    </div>
                    <div className="text-center px-3 py-2 rounded-md" style={{ backgroundColor: 'var(--bg-700)' }}>
                      <p className="text-lg font-bold" style={{ color: '#10b981' }}>
                        {result.out_of_scope_items?.length || 0}
                      </p>
                      <p className="text-[10px] font-mono themed-text-muted">EXCLUDED</p>
                    </div>
                  </div>
                </div>
              </div>

              {result.scope_summary && (
                <div className="mt-4 px-4 py-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
                  <h4 className="text-[10px] font-mono themed-text-muted uppercase tracking-wider mb-1">Scope Interpretation</h4>
                  <p className="text-sm themed-text-secondary">{result.scope_summary}</p>
                </div>
              )}
            </div>

            {/* High severity gaps */}
            {highGaps.length > 0 && (
              <div>
                <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#ef4444' }} />
                  High Severity Gaps ({highGaps.length})
                </h3>
                <div className="space-y-3">
                  {highGaps.map((g, i) => <GapCard key={i} gap={g} defaultOpen={true} />)}
                </div>
              </div>
            )}

            {/* Medium severity gaps */}
            {medGaps.length > 0 && (
              <div>
                <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#eab308' }} />
                  Medium Severity Gaps ({medGaps.length})
                </h3>
                <div className="space-y-3">
                  {medGaps.map((g, i) => <GapCard key={i} gap={g} />)}
                </div>
              </div>
            )}

            {/* Low severity gaps */}
            {lowGaps.length > 0 && (
              <div>
                <h3 className="text-xs font-mono themed-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#3b82f6' }} />
                  Low Severity Gaps ({lowGaps.length})
                </h3>
                <div className="space-y-3">
                  {lowGaps.map((g, i) => <GapCard key={i} gap={g} />)}
                </div>
              </div>
            )}

            {/* No gaps */}
            {gaps.length === 0 && (
              <div className="card p-8 text-center">
                <CheckCircle2 size={40} style={{ color: '#10b981' }} className="mx-auto mb-3" />
                <h3 className="text-base font-semibold themed-text-primary mb-1">Full Coverage</h3>
                <p className="text-sm themed-text-muted">No gaps detected against {result.methodology_name}. Nice work.</p>
              </div>
            )}

            {/* Out of scope items */}
            <OutOfScopeSection items={result.out_of_scope_items} />
          </div>
        )}
    </div>
  );
}
