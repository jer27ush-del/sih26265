import { createContext } from 'react';
import type { User } from './types';

export interface AuthValue {
  user: User | null;
  /** False until the saved session has been checked against the server. */
  ready: boolean;
  /** Demo accounts for the sign-in page and role switcher. Empty when demo mode is off. */
  demoUsers: User[];
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  switchRole: (userId: string) => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);
