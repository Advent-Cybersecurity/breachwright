import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { auth as authApi } from '../api';
import { ArrowRight, AlertCircle, Check, Shield } from 'lucide-react';

export default function Setup() {
  const navigate = useNavigate();
  const { markSetupComplete } = useAuth();
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 12) {
      setError('Password must be at least 12 characters.');
      return;
    }

    setLoading(true);
    try {
      await authApi.setup(email, password, displayName || email.split('@')[0]);
      markSetupComplete();
      setDone(true);
      setTimeout(() => navigate('/login'), 2000);
    } catch (err) {
      if (err.status === 403) {
        setError('Setup already completed. Redirecting to login...');
        setTimeout(() => navigate('/login'), 1500);
      } else {
        setError(err.message || 'Setup failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-900)' }}>
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full mb-5"
            style={{ backgroundColor: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
            <Check size={28} style={{ color: '#22c55e' }} />
          </div>
          <h2 className="text-xl font-bold themed-text-primary mb-2">Admin Account Created</h2>
          <p className="text-sm themed-text-muted">Redirecting to login...</p>
        </div>
      </div>
    );
  }

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
          <div className="flex items-center gap-2 mb-4">
            <Shield size={16} style={{ color: 'var(--accent-red)' }} />
            <h2 className="text-sm font-mono themed-text-muted uppercase tracking-wider">First Run Setup</h2>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 px-3 py-2.5 rounded-md bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                <AlertCircle size={16} className="shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div>
              <label htmlFor="setup-email" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Admin Email</label>
              <input id="setup-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="input-field font-mono text-sm" placeholder="admin@example.com" autoFocus required />
            </div>
            <div>
              <label htmlFor="setup-display-name" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Display Name</label>
              <input id="setup-display-name" type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                className="input-field font-mono text-sm" placeholder="Optional" />
            </div>
            <div>
              <label htmlFor="setup-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Password</label>
              <input id="setup-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="input-field font-mono text-sm" placeholder="Min 12 characters" minLength={12} maxLength={128} required />
            </div>
            <div>
              <label htmlFor="setup-confirm-password" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Confirm Password</label>
              <input id="setup-confirm-password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                className="input-field font-mono text-sm" required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
              {loading ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> :
                <><span>Create Admin Account</span><ArrowRight size={16} /></>}
            </button>
          </form>
        </div>
        <p className="text-center text-xs themed-text-muted mt-6 font-mono">FIRST TIME? CREATE YOUR ADMIN ACCOUNT</p>
      </div>
    </div>
  );
}
