import { useState, useEffect, useCallback, useRef } from 'react';
import { engagements as engApi, jobs as jobsApi, analysis as analysisApi } from '../api';
import { Toast, Spinner, SeverityBadge } from '../components/UI';
import {
  Play, Square, Trash2, Brain, Download, ChevronDown, ChevronRight,
  Terminal, Wifi, Globe, Link, Settings, AlertCircle, CheckCircle,
  Clock, Loader
} from 'lucide-react';

const TABS = [
  { id: 'network', label: 'Network Enum', icon: Wifi, tools: ['nmap'] },
  { id: 'recon', label: 'External Recon', icon: Globe, tools: ['subfinder', 'httpx', 'gowitness'] },
  { id: 'web', label: 'Web Enum', icon: Link, tools: ['nikto', 'feroxbuster', 'nuclei'] },
];

const STATUS_STYLES = {
  running: { color: '#eab308', label: 'RUNNING', icon: Loader },
  complete: { color: '#22c55e', label: 'COMPLETE', icon: CheckCircle },
  failed: { color: '#ef4444', label: 'FAILED', icon: AlertCircle },
  stopped: { color: '#f97316', label: 'STOPPED', icon: Square },
  queued: { color: '#71717a', label: 'QUEUED', icon: Clock },
};

function PresetCard({ preset, selected, onClick }) {
  return (
    <button onClick={onClick}
      className="p-3 rounded-md text-left transition-all text-sm"
      style={{
        backgroundColor: selected ? 'rgba(239,68,68,0.08)' : 'var(--bg-700)',
        border: `1px solid ${selected ? 'var(--accent-red)' : 'var(--bg-500)'}`,
      }}
    >
      <div className="font-semibold themed-text-primary text-xs">{preset.name}</div>
      <div className="themed-text-muted text-[11px] mt-0.5">{preset.description}</div>
    </button>
  );
}

function JobCard({ job, onStop, onDelete, onAnalyze, onDownloaded, onRefresh }) {
  const [expanded, setExpanded] = useState(job.status === 'running');
  const outputRef = useRef(null);
  const statusInfo = STATUS_STYLES[job.status] || STATUS_STYLES.queued;
  const StatusIcon = statusInfo.icon;

  // Auto-scroll terminal
  useEffect(() => {
    if (expanded && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [job.output, expanded]);

  // Poll for updates while running
  useEffect(() => {
    if (job.status !== 'running') return;
    const interval = setInterval(onRefresh, 2000);
    return () => clearInterval(interval);
  }, [job.status, onRefresh]);

  const elapsed = (() => {
    if (!job.started_at) return '';
    const start = new Date(job.started_at);
    const end = job.completed_at ? new Date(job.completed_at) : new Date();
    const secs = Math.floor((end - start) / 1000);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  })();

  return (
    <div className="card overflow-hidden mb-3">
      <button onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
        onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-700)'}
        onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
      >
        {/* Status dot */}
        <div className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{
            backgroundColor: statusInfo.color,
            animation: job.status === 'running' ? 'pulse 1.5s infinite' : 'none',
          }} />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="text-xs font-mono themed-text-primary truncate">{job.command}</div>
          <div className="text-[10px] font-mono themed-text-muted mt-0.5">
            {job.tool.toUpperCase()} // {job.status === 'running' ? 'started' : job.status} {elapsed && `// ${elapsed}`}
            {job.pid && ` // PID ${job.pid}`}
          </div>
        </div>

        {/* Status badge */}
        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded"
          style={{ backgroundColor: statusInfo.color + '20', color: statusInfo.color }}>
          {statusInfo.label}
        </span>

        {expanded ?
          <ChevronDown size={14} className="themed-text-muted shrink-0" /> :
          <ChevronRight size={14} className="themed-text-muted shrink-0" />
        }
      </button>

      {/* Progress bar for running jobs */}
      {job.status === 'running' && (
        <div style={{ height: 2, backgroundColor: 'var(--bg-600)' }}>
          <div style={{
            height: '100%', backgroundColor: '#eab308', borderRadius: 1,
            width: '100%', animation: 'pulse 2s infinite', opacity: 0.6,
          }} />
        </div>
      )}

      {expanded && (
        <>
          {/* Terminal output */}
          <div ref={outputRef}
            className="mx-4 mt-3 mb-3 p-3 rounded-md font-mono text-[11px] leading-relaxed overflow-auto whitespace-pre-wrap"
            style={{
              backgroundColor: '#0c0c12', border: '1px solid var(--bg-600)',
              maxHeight: 350, color: 'var(--text-secondary)',
            }}
          >
            {job.output || (job.status === 'running' ? 'Waiting for output...' : 'No output')}
            {job.status === 'running' && <span style={{ animation: 'pulse 1s infinite' }}> _</span>}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 px-4 py-3"
            style={{ borderTop: '1px solid var(--border)', backgroundColor: 'var(--bg-700)' }}>
            {job.status === 'running' ? (
              <>
                <button onClick={onStop} className="btn-ghost flex items-center gap-1.5 text-xs"
                  style={{ color: '#f97316' }}>
                  <Square size={12} /> Stop
                </button>
                <div style={{ flex: 1 }} />
                <button onClick={onDelete} className="btn-ghost flex items-center gap-1 text-xs"
                  style={{ color: 'var(--accent-red)' }}>
                  <Trash2 size={12} /> Delete
                </button>
              </>
            ) : (
              <>
                {job.status === 'complete' && ['nmap', 'nikto', 'feroxbuster', 'nuclei'].includes(job.tool) && (
                  <button onClick={onAnalyze} disabled={job._analyzing}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium"
                    style={{ backgroundColor: 'rgba(6,182,212,0.15)', color: '#06b6d4' }}>
                    {job._analyzing ? <Loader size={12} className="animate-spin" /> : <Brain size={12} />}
                    {job._analyzing ? 'Analyzing...' : 'Analyze with AI'}
                  </button>
                )}
                {job.status === 'complete' && job.output && (
                  <button onClick={() => {
                    const filename = `${job.tool}_${job.id.slice(0,8)}.txt`;
                    const blob = new Blob([job.output], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    a.click();
                    URL.revokeObjectURL(url);
                    onDownloaded(filename);
                  }}
                    className="btn-ghost flex items-center gap-1.5 text-xs">
                    <Download size={12} /> Download Output
                  </button>
                )}
                <div style={{ flex: 1 }} />
                <button onClick={onDelete} className="btn-ghost flex items-center gap-1 text-xs"
                  style={{ color: 'var(--accent-red)' }}>
                  <Trash2 size={12} /> Delete
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function ToolRunner() {
  const [engagementList, setEngagementList] = useState([]);
  const [selectedEng, setSelectedEng] = useState('');
  const [activeTab, setActiveTab] = useState('network');
  const [presets, setPresets] = useState({});
  const [jobList, setJobList] = useState([]);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(true);

  // Tool config state
  const [selectedPreset, setSelectedPreset] = useState('');
  const [selectedTool, setSelectedTool] = useState('');
  const [target, setTarget] = useState('');
  const [ports, setPorts] = useState('');
  const [timing, setTiming] = useState('T3');
  const [customCmd, setCustomCmd] = useState('');
  const [editingCmd, setEditingCmd] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [engs, psets] = await Promise.all([engApi.list(), jobsApi.presets()]);
        setEngagementList(engs);
        setPresets(psets);
        if (engs.length > 0) {
          setSelectedEng(engs[0].id);
          setTarget(engs[0].scope?.trim() || '');
        }
      } catch (e) {}
      finally { setLoading(false); }
    })();
  }, []);

  // Load jobs when engagement changes
  useEffect(() => {
    if (!selectedEng) return;
    jobsApi.list(selectedEng).then(setJobList).catch(() => {});
  }, [selectedEng]);

  const refreshJobs = useCallback(async () => {
    if (!selectedEng) return;
    try {
      const jobs = await jobsApi.list(selectedEng);
      setJobList(jobs);
    } catch (e) {}
  }, [selectedEng]);

  // Build command from inputs
  const tabTools = TABS.find(t => t.id === activeTab)?.tools || ['nmap'];
  const currentTool = selectedTool && tabTools.includes(selectedTool) ? selectedTool : tabTools[0];
  const toolPresets = presets[currentTool]?.presets || {};
  const toolAvailable = presets[currentTool]?.available || false;

  const buildCommand = useCallback(() => {
    if (editingCmd && customCmd) return customCmd;

    const preset = toolPresets[selectedPreset];
    if (!preset) return '';

    let cmd = preset.cmd;
    cmd = cmd.replace('{target}', target || 'TARGET');
    cmd = cmd.replace('{output_file}', 'output.txt');
    cmd = cmd.replace('{output_dir}', '.');
    cmd = cmd.replace('{input_file}', 'input.txt');

    // Nmap-specific: inject timing and ports
    if (currentTool === 'nmap') {
      if (ports) {
        cmd = cmd.replace(/--top-ports \d+/, `-p ${ports}`);
        cmd = cmd.replace(/-p-/, `-p ${ports}`);
      }
      cmd = cmd.replace(/-T\d/, `-${timing}`);
    }

    return cmd;
  }, [selectedPreset, target, ports, timing, toolPresets, currentTool, editingCmd, customCmd]);

  const command = buildCommand();

  // Auto-select first preset when tab or tool changes
  useEffect(() => {
    const keys = Object.keys(toolPresets);
    if (keys.length > 0 && !keys.includes(selectedPreset)) {
      setSelectedPreset(keys[0]);
    }
  }, [activeTab, currentTool, toolPresets, selectedPreset]);

  // Reset tool when tab changes
  useEffect(() => {
    const tools = TABS.find(t => t.id === activeTab)?.tools || [];
    if (tools.length > 0) setSelectedTool(tools[0]);
  }, [activeTab]);

  const handleRun = async () => {
    if (!command.trim() || !selectedEng) return;
    setRunning(true);
    try {
      const job = await jobsApi.create(selectedEng, currentTool, command);
      setJobList(prev => [job, ...prev]);
      setToast({ message: `${currentTool} started (PID ${job.pid})`, type: 'success' });
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    } finally {
      setRunning(false);
    }
  };

  const handleStop = async (jobId) => {
    try {
      await jobsApi.stop(jobId);
      await refreshJobs();
      setToast({ message: 'Job stopped', type: 'success' });
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    }
  };

  const handleDelete = async (jobId) => {
    try {
      await jobsApi.delete(jobId);
      setJobList(prev => prev.filter(j => j.id !== jobId));
      setToast({ message: 'Job deleted', type: 'success' });
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    }
  };

  const handleAnalyze = async (job) => {
    if (!job.output) return;
    const engName = engagementList.find(e => e.id === selectedEng)?.name || 'engagement';

    // Mark as analyzing
    setJobList(prev => prev.map(j => j.id === job.id ? { ...j, _analyzing: true } : j));

    const blob = new Blob([job.output], { type: 'text/plain' });
    const file = new File([blob], `${job.tool}_output.txt`, { type: 'text/plain' });

    try {
      await analysisApi.uploadScan(selectedEng, file, job.tool);
      const result = await analysisApi.run(selectedEng);
      const count = result?.drafts?.length || 0;
      setToast({
        message: `${count} AI proposal${count !== 1 ? 's' : ''} ready for review in "${engName}" > Scans`,
        type: 'success',
      });
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    } finally {
      setJobList(prev => prev.map(j => j.id === job.id ? { ...j, _analyzing: false } : j));
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Spinner style={{ color: 'var(--accent-red)' }} /></div>;
  }

  const engForTarget = engagementList.find(e => e.id === selectedEng);

  // Stats
  const runningCount = jobList.filter(j => j.status === 'running').length;
  const completeCount = jobList.filter(j => j.status === 'complete').length;

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold themed-text-primary">Tool Runner</h1>
          <p className="text-sm themed-text-muted mt-1">Execute security tools and pipe results into AI analysis</p>
        </div>
      </div>

      <div className="mb-6 rounded p-3 text-xs themed-text-secondary"
        style={{ border: '1px solid color-mix(in srgb, #f59e0b 45%, var(--border))', backgroundColor: 'color-mix(in srgb, #f59e0b 8%, var(--bg-800))' }}>
        Commands run on the Breachwright host with the permissions of the Breachwright process.
        Keep Breachwright on a trusted local machine. Review every command and target before running it.
      </div>

      {/* Engagement selector */}
      <div className="flex items-center gap-3 mb-6">
        <label htmlFor="tool-engagement" className="text-xs font-mono themed-text-muted uppercase tracking-wider">Engagement:</label>
        <select id="tool-engagement" className="input-field text-sm" style={{ maxWidth: 400 }}
          value={selectedEng}
          onChange={(e) => {
            setSelectedEng(e.target.value);
            const eng = engagementList.find(en => en.id === e.target.value);
            if (eng?.scope) setTarget(eng.scope.trim());
          }}>
          {engagementList.map(eng => (
            <option key={eng.id} value={eng.id}>{eng.name} ({eng.client_name})</option>
          ))}
        </select>
      </div>

      {/* Tool tabs */}
      <div className="flex mb-5" style={{ borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
              style={{
                borderColor: activeTab === tab.id ? 'var(--accent-red)' : 'transparent',
                color: activeTab === tab.id ? 'var(--accent-red)' : 'var(--text-muted)',
              }}>
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tool configuration */}
      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-mono themed-text-muted uppercase tracking-wider">
            {currentTool.toUpperCase()} Configuration
          </div>
          {!toolAvailable && (
            <span className="text-xs px-2 py-1 rounded font-mono"
              style={{ backgroundColor: 'rgba(239,68,68,0.15)', color: '#ef4444' }}>
              NOT INSTALLED
            </span>
          )}
        </div>

        {/* Tool selector (when tab has multiple tools) */}
        {tabTools.length > 1 && (
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs font-mono themed-text-muted">Tool:</span>
            {tabTools.map(tool => (
              <button key={tool} onClick={() => { setSelectedTool(tool); setSelectedPreset(''); setEditingCmd(false); }}
                className="text-xs font-mono font-medium px-3 py-1.5 rounded-md transition-colors"
                style={{
                  backgroundColor: currentTool === tool ? 'rgba(239,68,68,0.15)' : 'var(--bg-700)',
                  color: currentTool === tool ? 'var(--accent-red)' : 'var(--text-muted)',
                  border: `1px solid ${currentTool === tool ? 'rgba(239,68,68,0.3)' : 'var(--bg-500)'}`,
                }}>
                {tool}
                {presets[tool] && !presets[tool].available && (
                  <span className="ml-1 opacity-50">✗</span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Presets */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mb-4">
          {Object.entries(toolPresets).map(([key, preset]) => (
            <PresetCard key={key} preset={preset}
              selected={selectedPreset === key}
              onClick={() => { setSelectedPreset(key); setEditingCmd(false); }}
            />
          ))}
          <PresetCard
            preset={{ name: 'Custom', description: 'Enter your own command' }}
            selected={editingCmd}
            onClick={() => { setEditingCmd(true); setCustomCmd(command); }}
          />
        </div>

        {/* Inputs */}
        <div className="flex gap-3 mb-4">
          <div className="flex-1">
            <label htmlFor="tool-target" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
              Target
            </label>
            <input id="tool-target" className="input-field font-mono text-sm" value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={activeTab === 'web' ? 'http://target:port' : activeTab === 'recon' ? 'example.com' : 'IP, CIDR, or hostname'}
            />
          </div>
          {currentTool === 'nmap' && (
            <>
              <div style={{ width: 140 }}>
                <label htmlFor="tool-ports" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                  Ports
                </label>
                <input id="tool-ports" className="input-field font-mono text-sm" value={ports}
                  onChange={(e) => setPorts(e.target.value)}
                  placeholder="Default" />
              </div>
              <div style={{ width: 80 }}>
                <label htmlFor="tool-timing" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                  Timing
                </label>
                <select id="tool-timing" className="input-field text-sm" value={timing}
                  onChange={(e) => setTiming(e.target.value)}>
                  {['T1', 'T2', 'T3', 'T4', 'T5'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </>
          )}
        </div>

        {/* Command preview */}
        {editingCmd ? (
          <div className="mb-4">
            <label htmlFor="tool-custom-command" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
              Command
            </label>
            <input id="tool-custom-command" className="input-field font-mono text-sm" value={customCmd}
              onChange={(e) => setCustomCmd(e.target.value)}
              placeholder="Enter full command..." />
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-md mb-4 font-mono text-xs"
            style={{ backgroundColor: 'var(--bg-900)', border: '1px solid var(--bg-600)' }}>
            <span style={{ color: '#22c55e' }}>$</span>
            <span style={{ color: '#06b6d4' }}>{command || 'Select a preset and enter a target'}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 justify-end">
          {!editingCmd && (
            <button onClick={() => { setEditingCmd(true); setCustomCmd(command); }}
              className="btn-ghost text-xs">
              Edit Command
            </button>
          )}
          {editingCmd && (
            <button onClick={() => setEditingCmd(false)}
              className="btn-ghost text-xs">
              Use Preset
            </button>
          )}
          <button onClick={handleRun} disabled={running || !command.trim() || !target.trim()}
            className="btn-primary flex items-center gap-2 text-sm">
            {running ? <Spinner className="w-4 h-4" /> : <Play size={14} />}
            {running ? 'Starting...' : 'Run'}
          </button>
        </div>
      </div>

      {/* Job history */}
      {jobList.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-mono themed-text-muted uppercase tracking-wider">
              Job History
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              {runningCount > 0 && (
                <span style={{ color: '#eab308' }}>{runningCount} running</span>
              )}
              <span className="themed-text-muted">{completeCount} completed</span>
            </div>
          </div>

          {jobList.map(job => (
            <JobCard key={job.id} job={job}
              onStop={() => handleStop(job.id)}
              onDelete={() => handleDelete(job.id)}
              onAnalyze={() => handleAnalyze(job)}
              onDownloaded={(filename) => setToast({ message: `Downloaded: ${filename}`, type: 'success' })}
              onRefresh={refreshJobs}
            />
          ))}
        </div>
      )}

      {jobList.length === 0 && (
        <div className="text-center py-12">
          <Terminal size={32} className="themed-text-muted mx-auto mb-3" />
          <p className="text-sm themed-text-secondary">No jobs yet</p>
          <p className="text-xs themed-text-muted mt-1">Configure a tool above and click Run to start</p>
        </div>
      )}

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
