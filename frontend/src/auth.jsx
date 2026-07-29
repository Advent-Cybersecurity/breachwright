import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { auth as authApi, setToken, setAuthErrorHandler } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (e) { /* ignore */ }
    setToken(null);
    setUser(null);
  }, []);

  // Try refreshing token on mount
  useEffect(() => {
    setAuthErrorHandler(logout);

    (async () => {
      try {
        const tokens = await authApi.refresh();
        setToken(tokens.access_token);
        const me = await authApi.me();
        setUser(me);
      } catch (e) {
        // No valid session
      } finally {
        setLoading(false);
      }
    })();
  }, [logout]);

  const login = async (email, password) => {
    const tokens = await authApi.login(email, password);
    setToken(tokens.access_token);
    const me = await authApi.me();
    setUser(me);
    return me;
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
