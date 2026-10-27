import type { User } from '../types';
import { api, clearToken, getToken, setToken } from './http';

export function hasToken(): boolean {
  return Boolean(getToken());
}

export const authApi = {
  async login(email: string, password: string): Promise<User> {
    const result = await api<{ token: string; user: User }>('/auth/login/', { method: 'POST', body: { email, password }, auth: false });
    setToken(result.token);
    return result.user;
  },
  async logout(): Promise<void> {
    try {
      await api('/auth/logout/', { method: 'POST' });
    } finally {
      clearToken();
    }
  },
  me: (): Promise<User> => api<User>('/auth/me/'),
  demoUsers: (): Promise<User[]> => api<User[]>('/auth/demo-users/', { auth: false }),
  async demoSwitch(userId: string): Promise<User> {
    const result = await api<{ token: string; user: User }>('/auth/demo-switch/', { method: 'POST', body: { userId }, auth: false });
    setToken(result.token);
    return result.user;
  }
};
