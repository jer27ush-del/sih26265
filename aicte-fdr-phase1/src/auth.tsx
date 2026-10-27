import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { User } from './types';
import { authApi, hasToken } from './api/authApi';
import { AuthContext, type AuthValue } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [demoUsers, setDemoUsers] = useState<User[]>([]);
  const [ready, setReady] = useState(false);

  // On first load, restore the session from the saved token and fetch the demo account list.
  useEffect(() => {
    let active = true;
    async function restore() {
      const me = hasToken() ? await authApi.me().catch(() => null) : null;
      const demo = await authApi.demoUsers().catch(() => [] as User[]);
      if (active) {
        setUser(me);
        setDemoUsers(demo);
        setReady(true);
      }
    }
    void restore();
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthValue>(() => ({
    user,
    ready,
    demoUsers,
    async login(email, password) {
      setUser(await authApi.login(email, password));
    },
    async logout() {
      await authApi.logout();
      setUser(null);
    },
    async switchRole(userId) {
      setUser(await authApi.demoSwitch(userId));
    }
  }), [user, ready, demoUsers]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
