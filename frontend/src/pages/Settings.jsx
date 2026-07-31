import { useState, useEffect } from 'react';
import { system, auth as authApi, appSettings } from '../api';
import { useAuth } from '../auth';
import { useTheme } from '../theme';
import { Modal, Toast, Spinner } from '../components/UI';
import { Users, Server, UserPlus, Sun, Moon, Palette, MessageSquare, RotateCcw, Bot, Save, Wifi, WifiOff, RefreshCw, DatabaseBackup, Download, ShieldCheck, KeyRound } from 'lucide-react';

function InfoRow({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid color-mix(in srgb, var(--border) 40%, transparent)' }}>
      <span className="text-sm themed-text-muted">{label}</span>
      <span className={`text-sm themed-text-primary text-right break-all max-w-[70%] ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

export default function Settings() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [health, setHealth] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [backups, setBackups] = useState([]);
  const [backingUp, setBackingUp] = useState(false);
  const [pendingBackupDelete, setPendingBackupDelete] = useState(null);
  const [deletingBackup, setDeletingBackup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showAddUser, setShowAddUser] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current: '',
    next: '',
    confirm: '',
  });
  const [changingPassword, setChangingPassword] = useState(false);
  const [toast, setToast] = useState(null);
  const [userAccounts, setUserAccounts] = useState([]);
  const [userForm, setUserForm] = useState({ email: '', password: '', display_name: '', role: 'analyst' });
  const [addingUser, setAddingUser] = useState(false);
  const [updatingUserId, setUpdatingUserId] = useState(null);
  const [prompts, setPrompts] = useState(null);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [promptDraft, setPromptDraft] = useState('');
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [provider, setProvider] = useState(null);
  const [providerForm, setProviderForm] = useState({});
  const [savingProvider, setSavingProvider] = useState(false);
  const [localStatus, setLocalStatus] = useState(null);
  const [checkingLocal, setCheckingLocal] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setHealth(await system.health());
      } catch (e) {}
      try {
        setDiagnostics(await system.diagnostics());
      } catch (e) {}
      if (user?.role === 'admin') {
        try {
          setBackups(await system.listBackups());
        } catch (e) {}
        try {
          setUserAccounts(await authApi.listUsers());
        } catch (e) {}
      }
      try {
        const p = await appSettings.getPrompts();
        setPrompts(p);
      } catch (e) {}
      try {
        const prov = await appSettings.getProvider();
        setProvider(prov);
        setProviderForm(prov);
      } catch (e) {}
      finally { setLoading(false); }
    })();
  }, [user?.role]);

  const handleAddUser = async (e) => {
    e.preventDefault();
    setAddingUser(true);
    try {
      const created = await authApi.createUser(userForm);
      setUserAccounts(prev => [...prev, created].sort((a, b) => a.email.localeCompare(b.email)));
      setShowAddUser(false);
      setUserForm({ email: '', password: '', display_name: '', role: 'analyst' });
      setToast({ message: 'User created', type: 'success' });
    } catch (err) { setToast({ message: err.message, type: 'error' }); }
    finally { setAddingUser(false); }
  };

  const handleUpdateUser = async (account, changes) => {
    setUpdatingUserId(account.id);
    try {
      const updated = await authApi.updateUser(account.id, changes);
      setUserAccounts(prev => prev.map(item => item.id === updated.id ? updated : item));
      setToast({ message: `${updated.display_name} updated`, type: 'success' });
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    } finally {
      setUpdatingUserId(null);
    }
  };

  const handleChangePassword = async (event) => {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.confirm) {
      setToast({ message: 'New passwords do not match', type: 'error' });
      return;
    }
    setChangingPassword(true);
    try {
      await authApi.changePassword(passwordForm.current, passwordForm.next);
      setShowChangePassword(false);
      setPasswordForm({ current: '', next: '', confirm: '' });
      await logout();
    } catch (err) {
      setToast({ message: err.message, type: 'error' });
    } finally {
      setChangingPassword(false);
    }
  };

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
      {user?.role === 'admin' && provider && (
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
                <option value="local">Local Model (Ollama / vLLM / LM Studio)</option>
              </select>
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
                  <select id="anthropic-model" className="input-field text-sm" style={{ maxWidth: 350 }}
                    value={providerForm.anthropic_model || 'claude-sonnet-4-20250514'}
                    onChange={(e) => setProviderForm(prev => ({ ...prev, anthropic_model: e.target.value }))}>
                    <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                    <option value="claude-opus-4-6">Claude Opus 4.6</option>
                    <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
                  </select>
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
                        ? `Connected — ${localStatus.server_type}${localStatus.models?.length ? ` (${localStatus.models.length} model${localStatus.models.length !== 1 ? 's' : ''})` : ''}`
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
                  if (providerForm.local_model_url) update.local_model_url = providerForm.local_model_url;
                  if (providerForm.local_model_name) update.local_model_name = providerForm.local_model_name;
                  if (providerForm.local_model_api_key) update.local_model_api_key = providerForm.local_model_api_key;
                  if (providerForm.local_model_timeout) update.local_model_timeout = providerForm.local_model_timeout;
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
        <div className="flex items-center gap-2.5 mb-4">
          <Server size={18} className="text-blue-400" />
          <h2 className="text-base font-semibold themed-text-primary">System</h2>
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
                <InfoRow label="Data directory" value={diagnostics.data_directory} mono />
                <InfoRow label="Free space" value={`${(diagnostics.free_space / (1024 ** 3)).toFixed(1)} GB`} mono />
              </>
            )}
          </div>
        )}
      </div>

      {/* Account security */}
      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <KeyRound size={18} className="text-yellow-400" />
            <div>
              <h2 className="text-base font-semibold themed-text-primary">Account Security</h2>
              <p className="text-xs themed-text-muted mt-0.5">
                Changing your password signs out every session for this account.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowChangePassword(true)}
            className="btn-secondary text-sm whitespace-nowrap"
          >
            Change Password
          </button>
        </div>
      </div>

      {/* Data safety */}
      {user?.role === 'admin' && (
        <div className="card p-5 mb-5">
          <div className="flex items-center gap-2.5 mb-2">
            <DatabaseBackup size={18} className="text-green-400" />
            <h2 className="text-base font-semibold themed-text-primary">Data Safety</h2>
          </div>
          <p className="text-xs themed-text-muted mb-4">
            Create a verified local backup of the database, evidence, uploads, reports, template assets, and Tool Runner output. API keys and signing secrets are excluded.
          </p>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-xs themed-text-secondary">
              <ShieldCheck size={14} className="text-green-400" />
              {backups.length} verified backup{backups.length === 1 ? '' : 's'}
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
              {backups.slice(0, 5).map(backup => (
                <div key={backup.filename} className="flex items-center gap-3 px-3 py-2 rounded-md"
                  style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono themed-text-primary truncate">{backup.filename}</p>
                    <p className="text-[10px] themed-text-muted">
                      {new Date(backup.created_at).toLocaleString()} · {(backup.size / (1024 ** 2)).toFixed(2)} MB
                    </p>
                  </div>
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
      )}

      {/* Custom AI Prompts */}
      {user?.role === 'admin' && prompts && (
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

      {/* User Management */}
      {user?.role === 'admin' && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <Users size={18} className="text-cyan-400" />
              <h2 className="text-base font-semibold themed-text-primary">User Management</h2>
            </div>
            <button onClick={() => setShowAddUser(true)} className="btn-secondary flex items-center gap-2 text-sm">
              <UserPlus size={14} /> Add User
            </button>
          </div>
          <p className="text-sm themed-text-muted">
            Manage user accounts. Breachwright does not impose a seat limit.
          </p>
          <div className="mt-4 space-y-2">
            {userAccounts.map(account => {
              const isCurrentUser = account.id === user.id;
              const isUpdating = updatingUserId === account.id;
              return (
                <div
                  key={account.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-3 px-3 py-3 rounded-md"
                  style={{
                    backgroundColor: 'var(--bg-700)',
                    border: '1px solid var(--border)',
                    opacity: account.is_active ? 1 : 0.65,
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm themed-text-primary truncate">
                      {account.display_name}
                      {isCurrentUser && <span className="text-xs themed-text-muted ml-1">(you)</span>}
                    </p>
                    <p className="text-xs themed-text-muted truncate">{account.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      aria-label={`Role for ${account.display_name}`}
                      className="input-field text-xs py-1.5"
                      style={{ width: 105 }}
                      value={account.role}
                      disabled={isCurrentUser || isUpdating}
                      onChange={(event) => handleUpdateUser(account, { role: event.target.value })}
                    >
                      <option value="admin">Admin</option>
                      <option value="analyst">Analyst</option>
                      <option value="viewer">Viewer</option>
                    </select>
                    <button
                      type="button"
                      aria-label={`${account.is_active ? 'Deactivate' : 'Reactivate'} ${account.display_name}`}
                      className="btn-secondary text-xs min-w-[84px]"
                      disabled={isCurrentUser || isUpdating}
                      onClick={() => handleUpdateUser(account, { is_active: !account.is_active })}
                    >
                      {isUpdating ? 'Saving...' : account.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <Modal open={showAddUser} onClose={() => setShowAddUser(false)} title="Add User">
            <form onSubmit={handleAddUser} className="space-y-4">
              <div>
                <label htmlFor="new-user-email" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Email</label>
                <input id="new-user-email" className="input-field text-sm" type="email" value={userForm.email}
                  onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} required autoFocus />
              </div>
              <div>
                <label htmlFor="new-user-display-name" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Display Name</label>
                <input id="new-user-display-name" className="input-field text-sm" value={userForm.display_name}
                  onChange={(e) => setUserForm({ ...userForm, display_name: e.target.value })} required />
              </div>
              <div>
                <label htmlFor="new-user-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Password</label>
                <input id="new-user-password" className="input-field text-sm" type="password" value={userForm.password}
                  onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} required minLength={12} />
                <p className="text-xs themed-text-muted mt-1">At least 12 characters.</p>
              </div>
              <div>
                <label htmlFor="new-user-role" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Role</label>
                <select id="new-user-role" className="input-field text-sm" value={userForm.role}
                  onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}>
                  <option value="analyst">Analyst</option>
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowAddUser(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={addingUser} className="btn-primary flex items-center gap-2">
                  {addingUser && <Spinner className="w-4 h-4" />} Create User
                </button>
              </div>
            </form>
          </Modal>
        </div>
      )}

      <Modal
        open={showChangePassword}
        onClose={() => setShowChangePassword(false)}
        title="Change Password"
      >
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label htmlFor="current-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
              Current Password
            </label>
            <input
              id="current-password"
              className="input-field text-sm"
              type="password"
              autoComplete="current-password"
              value={passwordForm.current}
              onChange={(event) => setPasswordForm({ ...passwordForm, current: event.target.value })}
              required
              autoFocus
            />
          </div>
          <div>
            <label htmlFor="next-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
              New Password
            </label>
            <input
              id="next-password"
              className="input-field text-sm"
              type="password"
              autoComplete="new-password"
              minLength={12}
              value={passwordForm.next}
              onChange={(event) => setPasswordForm({ ...passwordForm, next: event.target.value })}
              required
            />
            <p className="text-xs themed-text-muted mt-1">At least 12 characters.</p>
          </div>
          <div>
            <label htmlFor="confirm-next-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">
              Confirm New Password
            </label>
            <input
              id="confirm-next-password"
              className="input-field text-sm"
              type="password"
              autoComplete="new-password"
              minLength={12}
              value={passwordForm.confirm}
              onChange={(event) => setPasswordForm({ ...passwordForm, confirm: event.target.value })}
              required
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setShowChangePassword(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={changingPassword}
              className="btn-primary flex items-center gap-2"
            >
              {changingPassword && <Spinner className="w-4 h-4" />}
              Change Password
            </button>
          </div>
        </form>
      </Modal>

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
