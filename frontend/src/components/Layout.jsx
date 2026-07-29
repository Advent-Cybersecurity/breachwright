import { useState, useEffect } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { useTheme } from '../theme';
import { system } from '../api';
import {
  LayoutDashboard, Settings, LogOut, Sun, Moon, Terminal, Bot, ArrowUpCircle, Brain
} from 'lucide-react';

function SidebarLink({ to, icon: Icon, label, end = false }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-150 group
        ${isActive
          ? 'text-[var(--accent-red)] border-l-2 border-[var(--accent-red)] -ml-px'
          : 'themed-text-secondary hover:themed-text-primary'
        }`
      }
      style={({ isActive }) => isActive ? { backgroundColor: 'rgba(239,68,68,0.1)' } : {}}
    >
      <Icon size={18} className="shrink-0" />
      <span>{label}</span>
    </NavLink>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [updateInfo, setUpdateInfo] = useState(null);

  useEffect(() => {
    system.versionCheck().then(info => {
      if (info.update_available) setUpdateInfo(info);
    }).catch(() => {});
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: 'var(--bg-900)' }}>
      {/* Sidebar */}
      <aside className="w-60 flex flex-col fixed h-full z-20 themed-border"
        style={{ backgroundColor: 'var(--bg-800)', borderRight: '1px solid var(--border)' }}>
        {/* Logo */}
        <div className="px-4 py-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center overflow-hidden shrink-0"
              style={{ backgroundColor: '#0a0a0f' }}>
              <svg viewBox="0 0 512 512" width="32" height="32">
                <rect width="512" height="512" rx="80" fill="#0a0a0f"/>
                <text x="226" y="275" textAnchor="middle" fontFamily="'Courier New', monospace"
                  fontWeight="700" fontSize="78" fill="#e4e4e7" letterSpacing="5">ADVENT</text>
                <text x="418" y="275" textAnchor="middle" fontFamily="'Courier New', monospace"
                  fontWeight="700" fontSize="78" fill="#ef4444">_</text>
              </svg>
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-wide themed-text-primary">BREACHWRIGHT</h1>
              <p className="text-[10px] font-mono themed-text-muted tracking-widest">ADVENT CYBERSECURITY</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          <SidebarLink to="/" icon={LayoutDashboard} label="Engagements" end />
          <SidebarLink to="/tools" icon={Terminal} label="Tool Runner" />
          <SidebarLink to="/assistant" icon={Bot} label="AI Assistant" />
          <SidebarLink to="/knowledge" icon={Brain} label="Knowledge Base" />
          <SidebarLink to="/settings" icon={Settings} label="Settings" />
        </nav>

        {/* Theme toggle + User + Logout */}
        <div className="px-3 py-4" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Theme toggle */}
          <button
            onClick={toggle}
            className="flex items-center gap-2 w-full px-3 py-2 mb-2 text-sm themed-text-muted rounded-md transition-colors"
            style={{ ':hover': { backgroundColor: 'var(--bg-600)' } }}
            onMouseEnter={e => e.target.style.backgroundColor = 'var(--bg-600)'}
            onMouseLeave={e => e.target.style.backgroundColor = 'transparent'}
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </button>

          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full flex items-center justify-center"
              style={{ backgroundColor: 'var(--bg-500)' }}>
              <span className="text-xs font-bold themed-text-secondary">
                {user?.display_name?.[0]?.toUpperCase() || '?'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium themed-text-primary truncate">{user?.display_name}</p>
              <p className="text-xs themed-text-muted font-mono">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-3 py-2 mt-1 text-sm themed-text-muted rounded-md transition-colors"
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-700)'; e.currentTarget.style.color = 'var(--accent-red)'; }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)'; }}
          >
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 ml-60">
        {updateInfo && (
          <div className="flex items-center justify-between gap-3 px-8 py-2.5"
            style={{ backgroundColor: 'rgba(6,182,212,0.1)', borderBottom: '1px solid rgba(6,182,212,0.2)' }}>
            <div className="flex items-center gap-2 text-sm" style={{ color: '#06b6d4' }}>
              <ArrowUpCircle size={16} />
              <span>Breachwright <strong>v{updateInfo.latest}</strong> is available (you have v{updateInfo.current})</span>
            </div>
            <a href={updateInfo.release_url} target="_blank" rel="noopener noreferrer"
              className="text-xs font-medium px-3 py-1 rounded"
              style={{ backgroundColor: 'rgba(6,182,212,0.15)', color: '#06b6d4' }}>
              Download Update
            </a>
          </div>
        )}
        <div className="p-8 max-w-[1400px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
