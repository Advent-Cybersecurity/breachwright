import { useState, useEffect } from 'react';
import { system, appSettings } from '../api';
import { useTheme } from '../theme';
import { Toast, Spinner } from '../components/UI';
import { AlertTriangle, Server, Sun, Moon, Palette, MessageSquare, RotateCcw, Bot, Save, Wifi, WifiOff, RefreshCw, DatabaseBackup, Download, ShieldCheck } from 'lucide-react';

function InfoRow({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 40%, transparent)' }}>
      <span className="text-sm themed-text-muted">{label}</span>
      <span className={`text-sm themed-text-primary text-right break-all max-w-[70%] ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

export default function Settings() {
  const { theme, toggle } = useTheme();
  const [health, setHealth] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [backups, setBackups] = useState([]);
  const [backingUp, setBackingUp] = useState(false);
  const [pendingBackupDelete, setPendingBackupDelete] = useState(null);
  const [deletingBackup, setDeletingBackup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [prompts, setPrompts] = useState(null);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [promptDraft, setPromptDraft] = useState('');
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [provider, setProvider] = useState(null);
  const [providerForm, setProviderForm] = useState({});
  const [savingProvider, setSavingProvider] = useState(false);
  const [localStatus, setLocalStatus] = useState(null);
  const [checkingLocal, setCheckingLocal] = useState(false);
  const [refreshingDiagnostics, setRefreshingDiagnostics] = useState(false);
  const [downloadingSupport, setDownloadingSupport] = useState(false);
  const validBackups = backups.filter(backup => backup.valid !== false);
  const invalidBackups = backups.filter(backup => backup.valid === false);
  const newestBackup = validBackups[0] || null;
  const newestBackupAgeDays = newestBackup
    ? Math.max(0, Math.floor((Date.now() - new Date(newestBackup.created_at).getTime()) / 86400000))
    : null;

  useEffect(() => {
    (async () => {
      const failures = [];
      try {
        setHealth(await system.health());
      } catch (e) { failures.push('health'); }
      try {
        setDiagnostics(await system.diagnostics());
      } catch (e) { failures.push('diagnostics'); }
      try {
        setBackups(await system.listBackups());
      } catch (e) { failures.push('backups'); }
      try {
        const p = await appSettings.getPrompts();
        setPrompts(p);
      } catch (e) { failures.push('prompts'); }
      try {
        const prov = await appSettings.getProvider();
        setProvider(prov);
        setProviderForm(prov);
      } catch (e) { failures.push('AI provider settings'); }
      finally {
        if (failures.length > 0) {
          setToast({
            message: `Could not load: ${failures.join(', ')}`,
            type: 'error',
          });
        }
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="flex items-center justify-center py-20"><Spinner style={{ color: 'var(--accent-red)' }} /></div>;

  return (
    <div className="animate-fade-in max-w-2xl">
      <h1 className="text-xl font-semibold themed-text-primary mb-6">Settings</h1>

      {/* Appearance */}
      <div className="card p-5 mb-5">
        <div className="flex items-center gap-2.5 mb-4">
          <Palette size={18} style={{ color: 'var(--accent-red)' }} />
          <h2 className="text-base font-semibold themed-text-primary">Appearance</h2>
        </div>
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm themed-text-primary">Theme</p>
            <p className="text-xs themed-text-muted">Switch between light and dark mode</p>
          </div>
          <button onClick={toggle} className="btn-secondary flex items-center gap-2 text-sm">
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
          </button>
        </div>
      </div>

      {/* AI Provider */}
      {provider && (
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-2.5 mb-4">
            <Bot size={18} className="text-cyan-400" />
            <h2 className="text-base font-semibold themed-text-primary">AI Provider</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label htmlFor="ai-provider" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Provider</label>
              <select id="ai-provider" className="input-field text-sm" style={{ maxWidth: 250 }}
                value={providerForm.ai_provider || 'anthropic'}
                onChange={(e) => setProviderForm(prev => ({ ...prev, ai_provider: e.target.value }))}>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI (GPT)</option>
                <option value="azure">Azure OpenAI</option>
                <option value="bedrock">Amazon Bedrock</option>
                <option value="local">Local Model (Ollama / vLLM / LM Studio)</option>
              </select>
            </div>
            <div className="flex items-start justify-between gap-4 px-4 py-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
              <div>
                <p className="text-sm themed-text-primary">Redact common secrets before AI requests</p>
                <p className="text-xs themed-text-muted mt-1">
                  Filters authorization and cookie headers, token fields, API keys, JWTs, and private keys locally. Original evidence remains unchanged.
                </p>
              </div>
              <input
                type="checkbox"
                className="mt-1"
                checked={providerForm.ai_redact_sensitive_data !== false}
                onChange={event => setProviderForm(previous => ({ ...previous, ai_redact_sensitive_data: event.target.checked }))}
                aria-label="Redact common secrets before AI requests"
              />
            </div>
            {(providerForm.ai_provider || 'anthropic') === 'anthropic' && (
              <>
                <div>
                  <label htmlFor="anthropic-api-key" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                    Anthropic API Key {provider.has_anthropic_key && <span className="text-green-500 ml-1">(configured)</span>}
                  </label>
                  <input id="anthropic-api-key" className="input-field text-sm font-mono" type="password"
                    placeholder={provider.has_anthropic_key ? 'Key is set (enter new to replace)' : 'sk-ant-api03-...'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, anthropic_api_key: e.target.value }))} />
                </div>
                <div>
                  <label htmlFor="anthropic-model" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Model</label>
                  <input id="anthropic-model" className="input-field text-sm font-mono"
                    value={providerForm.anthropic_model || 'claude-sonnet-4-20250514'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, anthropic_model: e.target.value }))}
                    placeholder="Provider model identifier" />
                </div>
              </>
            )}
            {providerForm.ai_provider === 'openai' && (
              <>
                <div>
                  <label htmlFor="openai-api-key" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                    OpenAI API Key {provider.has_openai_key && <span className="text-green-500 ml-1">(configured)</span>}
                  </label>
                  <input id="openai-api-key" className="input-field text-sm font-mono" type="password"
                    placeholder={provider.has_openai_key ? 'Key is set (enter new to replace)' : 'sk-...'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, openai_api_key: e.target.value }))} />
                </div>
                <div>
                  <label htmlFor="openai-model" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Model</label>
                  <input id="openai-model" className="input-field text-sm font-mono"
                    value={providerForm.openai_model || 'gpt-4o'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, openai_model: e.target.value }))}
                    placeholder="gpt-4o" />
                </div>
              </>
            )}
            {providerForm.ai_provider === 'azure' && (
              <>
                <div>
                  <label htmlFor="azure-openai-key" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                    Azure OpenAI API Key {provider.has_azure_openai_key && <span className="text-green-500 ml-1">(configured)</span>}
                  </label>
                  <input id="azure-openai-key" className="input-field text-sm font-mono" type="password"
                    placeholder={provider.has_azure_openai_key ? 'Key is set (enter new to replace)' : 'Enter API key'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, azure_openai_api_key: e.target.value }))} />
                </div>
                <div>
                  <label htmlFor="azure-openai-endpoint" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Endpoint</label>
                  <input id="azure-openai-endpoint" className="input-field text-sm font-mono"
                    value={providerForm.azure_openai_endpoint || ''}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, azure_openai_endpoint: e.target.value }))}
                    placeholder="https://resource.openai.azure.com" />
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="azure-openai-deployment" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Deployment</label>
                    <input id="azure-openai-deployment" className="input-field text-sm font-mono"
                      value={providerForm.azure_openai_deployment || ''}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, azure_openai_deployment: e.target.value }))}
                      placeholder="Deployment name" />
                  </div>
                  <div>
                    <label htmlFor="azure-openai-version" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">API version</label>
                    <input id="azure-openai-version" className="input-field text-sm font-mono"
                      value={providerForm.azure_openai_api_version || ''}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, azure_openai_api_version: e.target.value }))}
                      placeholder="Azure API version" />
                  </div>
                </div>
              </>
            )}
            {providerForm.ai_provider === 'bedrock' && (
              <>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="aws-region" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">AWS region</label>
                    <input id="aws-region" className="input-field text-sm font-mono"
                      value={providerForm.aws_region || 'us-east-1'}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, aws_region: e.target.value }))}
                      placeholder="us-east-1" />
                  </div>
                  <div>
                    <label htmlFor="bedrock-model-id" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Model ID</label>
                    <input id="bedrock-model-id" className="input-field text-sm font-mono"
                      value={providerForm.bedrock_model_id || ''}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, bedrock_model_id: e.target.value }))}
                      placeholder="Bedrock inference profile or model ID" />
                  </div>
                </div>
                <div className="px-4 py-3 rounded-lg text-xs themed-text-muted" style={{ backgroundColor: 'var(--bg-700)' }}>
                  Bedrock uses the standard AWS credential chain. Provider usage may incur AWS charges; Breachwright does not call it until you run an AI action.
                </div>
              </>
            )}
            {providerForm.ai_provider === 'local' && (
              <>
                {/* Status indicator */}
                <div className="flex items-center gap-3 px-4 py-3 rounded-lg"
                  style={{ backgroundColor: localStatus?.online ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                    border: `1px solid ${localStatus?.online ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                  {localStatus?.online
                    ? <Wifi size={16} style={{ color: '#10b981' }} />
                    : <WifiOff size={16} style={{ color: '#ef4444' }} />}
                  <div className="flex-1">
                    <span className="text-sm font-medium" style={{ color: localStatus?.online ? '#10b981' : '#ef4444' }}>
                      {localStatus === null ? 'Not checked' : localStatus.online
                        ? `Connected: ${localStatus.server_type}${localStatus.models?.length ? ` (${localStatus.models.length} model${localStatus.models.length !== 1 ? 's' : ''})` : ''}`
                        : 'Server offline'}
                    </span>
                    {localStatus?.error && !localStatus.online && (
                      <p className="text-xs themed-text-muted mt-0.5">{localStatus.error}</p>
                    )}
                  </div>
                  <button onClick={async () => {
                    setCheckingLocal(true);
                    try {
                      const status = await appSettings.localModelStatus();
                      setLocalStatus(status);
                    } catch { setLocalStatus({ online: false, error: 'Request failed' }); }
                    finally { setCheckingLocal(false); }
                  }} disabled={checkingLocal}
                    className="text-xs font-mono px-2 py-1 rounded flex items-center gap-1 transition-colors"
                    style={{ backgroundColor: 'var(--bg-600)' }}>
                    {checkingLocal ? <Spinner className="w-3 h-3" /> : <RefreshCw size={12} />}
                    Test
                  </button>
                </div>

                <div>
                  <label htmlFor="local-model-url" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                    Server URL
                  </label>
                  <input id="local-model-url" className="input-field text-sm font-mono"
                    value={providerForm.local_model_url || 'http://localhost:11434'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, local_model_url: e.target.value }))}
                    placeholder="http://localhost:11434" />
                  <p className="text-xs themed-text-muted mt-1">
                    Ollama: :11434 • vLLM: :8000 • LM Studio: :1234 • llama.cpp: :8080
                  </p>
                </div>

                <div>
                  <label htmlFor="local-model-name" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                    Model
                  </label>
                  {localStatus?.online && localStatus.models?.length > 0 ? (
                    <select id="local-model-name" className="input-field text-sm font-mono"
                      value={providerForm.local_model_name || ''}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, local_model_name: e.target.value }))}>
                      <option value="">Select a model...</option>
                      {localStatus.models.map(m => (
                        <option key={m.name} value={m.name}>{m.name}{m.size ? ` (${(m.size / 1e9).toFixed(1)}GB)` : ''}</option>
                      ))}
                    </select>
                  ) : (
                    <input id="local-model-name" className="input-field text-sm font-mono"
                      value={providerForm.local_model_name || 'llama3.1'}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, local_model_name: e.target.value }))}
                      placeholder="llama3.1" />
                  )}
                  <p className="text-xs themed-text-muted mt-1">
                    {localStatus?.online ? 'Models detected from server' : 'Connect to server to see available models, or type a name'}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="local-model-api-key" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                      API Key <span className="normal-case">(optional)</span>
                    </label>
                    <input id="local-model-api-key" className="input-field text-sm font-mono" type="password"
                      placeholder="Most local servers don't need one"
                      onChange={(e) => setProviderForm(prev => ({ ...prev, local_model_api_key: e.target.value }))} />
                  </div>
                  <div>
                    <label htmlFor="local-model-timeout" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
                      Timeout <span className="normal-case">(seconds)</span>
                    </label>
                    <input id="local-model-timeout" className="input-field text-sm font-mono" type="number"
                      value={providerForm.local_model_timeout || 120}
                      onChange={(e) => setProviderForm(prev => ({ ...prev, local_model_timeout: parseInt(e.target.value) || 120 }))}
                      min={10} max={600} />
                  </div>
                </div>

                <div className="px-4 py-3 rounded-lg" style={{ backgroundColor: 'var(--bg-700)' }}>
                  <p className="text-xs themed-text-muted">
                    <strong className="themed-text-secondary">Quick start:</strong> Install <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" className="underline" style={{ color: 'var(--accent-red)' }}>Ollama</a>, then run:
                  </p>
                  <code className="block text-xs font-mono mt-1.5 px-2 py-1 rounded" style={{ backgroundColor: 'var(--bg-800)', color: '#10b981' }}>
                    ollama serve && ollama pull llama3.1
                  </code>
                </div>
              </>
            )}
            <div className="flex justify-end">
              <button onClick={async () => {
                setSavingProvider(true);
                try {
                  const update = {};
                  if (providerForm.ai_provider) update.ai_provider = providerForm.ai_provider;
                  if (providerForm.anthropic_api_key) update.anthropic_api_key = providerForm.anthropic_api_key;
                  if (providerForm.openai_api_key) update.openai_api_key = providerForm.openai_api_key;
                  if (providerForm.anthropic_model) update.anthropic_model = providerForm.anthropic_model;
                  if (providerForm.openai_model) update.openai_model = providerForm.openai_model;
                  if (providerForm.azure_openai_api_key) update.azure_openai_api_key = providerForm.azure_openai_api_key;
                  if (providerForm.azure_openai_endpoint) update.azure_openai_endpoint = providerForm.azure_openai_endpoint;
                  if (providerForm.azure_openai_deployment) update.azure_openai_deployment = providerForm.azure_openai_deployment;
                  if (providerForm.azure_openai_api_version) update.azure_openai_api_version = providerForm.azure_openai_api_version;
                  if (providerForm.aws_region) update.aws_region = providerForm.aws_region;
                  if (providerForm.bedrock_model_id) update.bedrock_model_id = providerForm.bedrock_model_id;
                  if (providerForm.local_model_url) update.local_model_url = providerForm.local_model_url;
                  if (providerForm.local_model_name) update.local_model_name = providerForm.local_model_name;
                  if (providerForm.local_model_api_key) update.local_model_api_key = providerForm.local_model_api_key;
                  if (providerForm.local_model_timeout) update.local_model_timeout = providerForm.local_model_timeout;
                  if (providerForm.ai_redact_sensitive_data !== undefined) update.ai_redact_sensitive_data = providerForm.ai_redact_sensitive_data;
                  await appSettings.updateProvider(update);
                  setToast({ message: 'Provider settings saved. Restart Breachwright for changes to take effect.', type: 'success' });
                } catch (err) { setToast({ message: err.message, type: 'error' }); }
                finally { setSavingProvider(false); }
              }} disabled={savingProvider} className="btn-primary flex items-center gap-2 text-sm">
                {savingProvider ? <Spinner className="w-4 h-4" /> : <Save size={14} />}
                Save Provider Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* System */}
      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <Server size={18} className="text-blue-400" />
            <h2 className="text-base font-semibold themed-text-primary">System</h2>
          </div>
          <div className="flex items-center gap-1">
            <button className="btn-ghost text-xs flex items-center gap-2" disabled={downloadingSupport} onClick={async () => {
              setDownloadingSupport(true);
              try {
                await system.downloadSupportSnapshot();
                setToast({ message: 'Privacy-bounded support snapshot downloaded', type: 'success' });
              } catch (err) {
                setToast({ message: `Support snapshot could not be downloaded: ${err.message}`, type: 'error' });
              } finally {
                setDownloadingSupport(false);
              }
            }} title="Download system and integrity metadata without logs, secrets, or workspace content">
              <Download size={13} /> {downloadingSupport ? 'Preparing...' : 'Support Snapshot'}
            </button>
            <button className="btn-ghost text-xs flex items-center gap-2" disabled={refreshingDiagnostics} onClick={async () => {
              setRefreshingDiagnostics(true);
              try {
                setDiagnostics(await system.diagnostics());
                setToast({ message: 'System and stored-file diagnostics refreshed', type: 'success' });
              } catch (err) {
                setToast({ message: `Diagnostics could not be refreshed: ${err.message}`, type: 'error' });
              } finally {
                setRefreshingDiagnostics(false);
              }
            }}>
              <RefreshCw size={13} className={refreshingDiagnostics ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        </div>
        {health && (
          <div>
            <InfoRow label="Status" value={
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green-400 pulse-dot" />
                <span className="text-green-400">{health.status}</span>
              </span>
            } />
            <InfoRow label="Version" value={health.version} mono />
            {diagnostics && (
              <>
                <InfoRow label="Platform" value={`${diagnostics.platform} ${diagnostics.platform_release}`} mono />
                <InfoRow label="Database" value={diagnostics.database_type} mono />
                {diagnostics.database_integrity && (
                  <InfoRow
                    label="Database integrity"
                    value={
                      <span className={diagnostics.database_integrity === 'ok' ? 'text-green-400' : 'text-yellow-400'}>
                        {diagnostics.database_integrity}
                      </span>
                    }
                    mono
                  />
                )}
                {diagnostics.stored_files && (
                  <InfoRow
                    label="Stored file integrity"
                    value={
                      <span className={diagnostics.stored_files.missing > 0 ? 'text-red-400' : diagnostics.stored_files.complete ? 'text-green-400' : 'text-yellow-400'}>
                        {diagnostics.stored_files.missing === 0
                          ? `${diagnostics.stored_files.checked} checked, none missing${diagnostics.stored_files.complete ? '' : ' (partial check)'}`
                          : `${diagnostics.stored_files.missing} missing of ${diagnostics.stored_files.checked} checked`}
                      </span>
                    }
                    mono
                  />
                )}
                <InfoRow label="Data directory" value={diagnostics.data_directory} mono />
                <InfoRow label="Free space" value={`${(diagnostics.free_space / (1024 ** 3)).toFixed(1)} GB`} mono />
              </>
            )}
          </div>
        )}
        <p className="text-[10px] themed-text-muted mt-3">
          Support snapshots exclude logs, credentials, the local data path, and all engagement content. Review any file before attaching it to a public issue.
        </p>
      </div>

      {/* Data safety */}
      <div className="card p-5 mb-5">
          <div className="flex items-center gap-2.5 mb-2">
            <DatabaseBackup size={18} className="text-green-400" />
            <h2 className="text-base font-semibold themed-text-primary">Data Safety</h2>
          </div>
          <p className="text-xs themed-text-muted mb-4">
            Create a verified local backup of the database, finding and notebook attachments, uploads, reports, template assets, and Tool Runner output. API keys and environment configuration are excluded.
          </p>
          {invalidBackups.length > 0 && (
            <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/5 px-3 py-2 flex items-start gap-2" role="alert">
              <AlertTriangle size={14} className="text-red-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs themed-text-primary">
                  {invalidBackups.length} stored backup{invalidBackups.length === 1 ? '' : 's'} failed verification.
                </p>
                <p className="text-[10px] themed-text-muted mt-0.5">
                  These archives are listed below so you can remove them. Create and download a fresh verified backup before relying on recovery.
                </p>
              </div>
            </div>
          )}
          <div className={`mb-4 rounded-md border px-3 py-2 flex items-start gap-2 ${
            newestBackupAgeDays === null || newestBackupAgeDays > 30
              ? 'border-red-500/40 bg-red-500/5'
              : newestBackupAgeDays > 7
                ? 'border-yellow-500/40 bg-yellow-500/5'
                : 'border-green-500/30 bg-green-500/5'
          }`} role="status">
            {newestBackupAgeDays === null || newestBackupAgeDays > 7
              ? <AlertTriangle size={14} className={newestBackupAgeDays === null || newestBackupAgeDays > 30 ? 'text-red-400 mt-0.5' : 'text-yellow-400 mt-0.5'} />
              : <ShieldCheck size={14} className="text-green-400 mt-0.5" />}
            <div>
              <p className="text-xs themed-text-primary">
                {newestBackupAgeDays === null
                  ? 'No verified backup is stored in this workspace.'
                  : newestBackupAgeDays === 0
                    ? 'The newest verified backup was created today.'
                    : `The newest verified backup is ${newestBackupAgeDays} day${newestBackupAgeDays === 1 ? '' : 's'} old.`}
              </p>
              <p className="text-[10px] themed-text-muted mt-0.5">
                Create a fresh backup before upgrades, workstation moves, or large imports.
              </p>
            </div>
          </div>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-xs themed-text-secondary">
              <ShieldCheck size={14} className="text-green-400" />
              {validBackups.length} verified backup{validBackups.length === 1 ? '' : 's'}
              {invalidBackups.length > 0 && (
                <span className="text-red-400">{invalidBackups.length} invalid</span>
              )}
            </div>
            <button
              onClick={async () => {
                setBackingUp(true);
                try {
                  const backup = await system.createBackup();
                  setBackups(prev => [backup, ...prev]);
                  setToast({ message: `Backup created: ${backup.filename}`, type: 'success' });
                } catch (err) {
                  setToast({ message: err.message, type: 'error' });
                } finally {
                  setBackingUp(false);
                }
              }}
              disabled={backingUp}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              {backingUp ? <Spinner className="w-4 h-4" /> : <DatabaseBackup size={14} />}
              {backingUp ? 'Creating...' : 'Create Backup'}
            </button>
          </div>
          {backups.length > 0 && (
            <div className="space-y-2">
              {backups.slice(0, 10).map(backup => (
                <div key={backup.filename} className="flex items-center gap-3 px-3 py-2 rounded-md"
                  style={{ backgroundColor: 'var(--bg-700)', border: `1px solid ${backup.valid === false ? 'rgb(239 68 68 / 0.4)' : 'var(--border)'}` }}>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono themed-text-primary truncate">{backup.filename}</p>
                    {backup.valid === false ? (
                      <>
                        <p className="text-[10px] text-red-400">Verification failed · {(backup.size / (1024 ** 2)).toFixed(2)} MB</p>
                        <p className="text-[10px] themed-text-muted truncate" title={backup.error}>{backup.error || 'Backup archive is invalid'}</p>
                      </>
                    ) : (
                      <p className="text-[10px] themed-text-muted">
                        {new Date(backup.created_at).toLocaleString()} · {(backup.size / (1024 ** 2)).toFixed(2)} MB · {backup.file_count ?? 0} protected file{backup.file_count === 1 ? '' : 's'}
                      </p>
                    )}
                  </div>
                  {backup.valid !== false && (
                    <button
                      onClick={async () => {
                        try {
                          await system.downloadBackup(backup.filename);
                        } catch (err) {
                          setToast({ message: err.message, type: 'error' });
                        }
                      }}
                      className="btn-ghost flex items-center gap-1 text-xs"
                    >
                      <Download size={12} />
                      Download
                    </button>
                  )}
                  {pendingBackupDelete === backup.filename ? (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="btn-ghost text-xs text-red-400"
                        disabled={deletingBackup}
                        onClick={async () => {
                          setDeletingBackup(true);
                          try {
                            await system.deleteBackup(backup.filename);
                            setBackups(prev => prev.filter(item => item.filename !== backup.filename));
                            setPendingBackupDelete(null);
                            setToast({ message: `Backup deleted: ${backup.filename}`, type: 'success' });
                          } catch (err) {
                            setToast({ message: err.message, type: 'error' });
                          } finally {
                            setDeletingBackup(false);
                          }
                        }}
                      >
                        {deletingBackup ? 'Deleting...' : 'Confirm delete'}
                      </button>
                      <button
                        type="button"
                        className="btn-ghost text-xs"
                        disabled={deletingBackup}
                        onClick={() => setPendingBackupDelete(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      aria-label={`Delete ${backup.filename}`}
                      className="btn-ghost text-xs text-red-400"
                      onClick={() => setPendingBackupDelete(backup.filename)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          <p className="text-[10px] themed-text-muted mt-3">
            Restores are intentionally offline. Stop Breachwright, then use BreachwrightCLI with the documented restore command.
          </p>
      </div>

      {/* Custom AI Prompts */}
      {prompts && (
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-2.5 mb-4">
            <MessageSquare size={18} className="text-cyan-400" />
            <h2 className="text-base font-semibold themed-text-primary">AI Prompts</h2>
          </div>
          <p className="text-xs themed-text-muted mb-4">
            Customize the system prompts used for scan analysis, attack path generation, and report writing.
          </p>
          {[
            { key: 'prompt_analysis', label: 'Scan Analysis Prompt' },
            { key: 'prompt_attack_paths', label: 'Attack Paths Prompt' },
            { key: 'prompt_reports', label: 'Report Generation Prompt' },
          ].map(({ key, label }) => (
            <div key={key} className="py-3" style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 40%, transparent)' }}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm themed-text-primary">{label}</span>
                <div className="flex items-center gap-2">
                  {editingPrompt === key ? (
                    <>
                      <button onClick={async () => {
                        setSavingPrompt(true);
                        try {
                          await appSettings.updatePrompt(key, promptDraft);
                          setPrompts(prev => ({ ...prev, [key]: promptDraft }));
                          setEditingPrompt(null);
                          setToast({ message: 'Prompt saved', type: 'success' });
                        } catch (err) { setToast({ message: err.message, type: 'error' }); }
                        finally { setSavingPrompt(false); }
                      }} disabled={savingPrompt} className="btn-primary text-xs px-3 py-1">
                        {savingPrompt ? <Spinner className="w-3 h-3" /> : 'Save'}
                      </button>
                      <button onClick={() => setEditingPrompt(null)} className="btn-ghost text-xs">Cancel</button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => { setEditingPrompt(key); setPromptDraft(prompts[key]); }}
                        className="btn-ghost text-xs">Edit</button>
                      <button onClick={async () => {
                        try {
                          const result = await appSettings.resetPrompt(key);
                          setPrompts(prev => ({ ...prev, [key]: result.value }));
                          setToast({ message: 'Prompt reset to default', type: 'success' });
                        } catch (err) { setToast({ message: err.message, type: 'error' }); }
                      }} className="themed-text-muted hover:text-orange-400 transition-colors p-1" title="Reset to default">
                        <RotateCcw size={13} />
                      </button>
                    </>
                  )}
                </div>
              </div>
              {editingPrompt === key ? (
                <textarea
                  className="input-field text-xs font-mono resize-y"
                  rows={10}
                  value={promptDraft}
                  onChange={(e) => setPromptDraft(e.target.value)}
                />
              ) : (
                <p className="text-xs themed-text-muted font-mono truncate">{prompts[key]?.substring(0, 120)}...</p>
              )}
            </div>
          ))}
        </div>
      )}

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
