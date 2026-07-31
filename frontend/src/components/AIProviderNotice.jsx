import { useCallback, useEffect, useState } from 'react';
import { Info, RefreshCw } from 'lucide-react';

import { appSettings } from '../api';


export function confirmAIAction(config, actionLabel) {
  if (!config || config.ai_redact_sensitive_data !== false) return Boolean(config);
  return window.confirm(
    `Sensitive-data redaction is off. ${actionLabel} context will be sent to ${config.ai_provider}. Continue?`
  );
}


export default function AIProviderNotice({ actionLabel, onConfigChange }) {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    onConfigChange(null);
    try {
      const next = await appSettings.getProvider();
      setConfig(next);
      onConfigChange(next);
    } catch (err) {
      setConfig(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [onConfigChange]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <div className="rounded border px-3 py-2 text-xs themed-text-muted" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-800)' }} role="status">
      Loading AI privacy settings...
    </div>;
  }

  if (error) {
    return <div className="rounded border border-yellow-500/40 bg-yellow-500/5 px-3 py-2 text-xs" role="alert">
      <span className="text-yellow-300">AI privacy settings unavailable: {error}</span>
      <span className="themed-text-muted"> This AI action is disabled until the local check succeeds.</span>
      <button className="btn-ghost text-xs ml-2 inline-flex items-center gap-1" onClick={load}>
        <RefreshCw size={11} /> Retry
      </button>
    </div>;
  }

  const externalProvider = config.ai_provider !== 'local';
  return <div className="flex items-start gap-2 rounded border px-3 py-2 text-xs themed-text-secondary" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-800)' }} role="status">
    <Info size={14} className="mt-0.5 shrink-0 text-cyan-400" />
    <span>
      Provider: <strong className="themed-text-primary">{config.ai_provider}</strong>
      {' / '}Local secret redaction: <strong className={config.ai_redact_sensitive_data ? 'text-green-400' : 'text-yellow-400'}>{config.ai_redact_sensitive_data ? 'on' : 'off'}</strong>
      {' / '}Starting {actionLabel} may send bounded engagement context to this provider.
      {externalProvider ? ' External provider usage may incur charges.' : ' The configured provider is local.'}
    </span>
  </div>;
}
