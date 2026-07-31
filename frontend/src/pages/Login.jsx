import { useState, useEffect } from 'react';
import { useAuth } from '../auth';
import { ArrowRight, AlertCircle } from 'lucide-react';


function VersionFooter() {
  const [version, setVersion] = useState('');
  useEffect(() => {
    fetch('/api/health').then(r => r.json()).then(d => setVersion(d.version || '')).catch(() => {});
  }, []);
  return <p className="text-center text-xs themed-text-muted mt-6 font-mono">{version ? `v${version}` : ''} // OPEN SOURCE</p>;
}

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try { await login(email, password); }
    catch (err) { setError(err.message || 'Authentication failed'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden"
      style={{ backgroundColor: 'var(--bg-900)' }}>
      <div className="absolute inset-0 scanline pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full blur-[120px]"
        style={{ backgroundColor: 'rgba(239,68,68,0.03)' }} />
      <div className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'linear-gradient(rgba(128,128,128,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(128,128,128,0.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px'
        }} />

      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl overflow-hidden mb-5 shadow-lg"
            style={{ boxShadow: '0 10px 25px rgba(0,0,0,0.2)', backgroundColor: '#0a0a0f' }}>
            <svg viewBox="0 0 512 512" width="64" height="64">
              <rect width="512" height="512" rx="80" fill="#0a0a0f"/>
              <text x="226" y="275" textAnchor="middle" fontFamily="'Courier New', monospace"
                fontWeight="700" fontSize="78" fill="#e4e4e7" letterSpacing="5">ADVENT</text>
              <text x="418" y="275" textAnchor="middle" fontFamily="'Courier New', monospace"
                fontWeight="700" fontSize="78" fill="#ef4444">_</text>
            </svg>
          </div>
          <h1 className="text-2xl font-bold tracking-wide themed-text-primary">BREACHWRIGHT</h1>
          <p className="text-xs font-mono themed-text-muted tracking-[0.3em] mt-1.5">ADVENT CYBERSECURITY</p>
        </div>

        <div className="card p-6" style={{ boxShadow: '0 10px 40px rgba(0,0,0,0.2)' }}>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 px-3 py-2.5 rounded-md bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                <AlertCircle size={16} className="shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div>
              <label htmlFor="login-email" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Email</label>
              <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="input-field font-mono text-sm" placeholder="operator@example.com" autoFocus required />
            </div>
            <div>
              <label htmlFor="login-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Password</label>
              <input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="input-field font-mono text-sm" required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
              {loading ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> :
                <><span>Authenticate</span><ArrowRight size={16} /></>}
            </button>
          </form>
        </div>
        <VersionFooter />
      </div>
    </div>
  );
}
