import type { AppSettings, AppStore, FDR, FDRStatus, Role } from '../types';
import { api } from './http';

export type FdrInput = Omit<FDR, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'reviewFlag'>;
export interface ImportResult { imported: number; skipped: { line: number; reason: string }[] }

/**
 * Workflow actions. Each call is one server request; the server applies the rules and writes the audit entry
 * in the same transaction. Signatures match the previous mock so the pages did not need redesigning.
 * The actor and role arguments are ignored: the server uses the signed-in user from the token.
 */
export const workflowApi = {
  /** Everything the workspace needs, already filtered by the server for this user's role. */
  list: (): Promise<AppStore> => api<AppStore>('/workspace/'),

  saveFdr: (input: FdrInput, _actorId: string): Promise<FDR> => api<FDR>('/fdrs/', { method: 'POST', body: input }),

  /** Bulk import. Sends the raw CSV text; the server parses it, validates each row and reports the rest. */
  importCsv: (text: string, _actorId: string): Promise<ImportResult> => {
    const form = new FormData();
    form.append('file', new File([text], 'import.csv', { type: 'text/csv' }));
    return api<ImportResult>('/fdrs/import/', { method: 'POST', form });
  },

  transition: (fdrId: string, status: FDRStatus, _actorId: string, _role: Role, reason = ''): Promise<FDR> =>
    api<FDR>(`/fdrs/${fdrId}/transition/`, { method: 'POST', body: { status, reason } }),

  bankConfirm: (fdrId: string, _actorId: string, date: string, officer: string, mode: string, reference: string): Promise<unknown> =>
    api(`/fdrs/${fdrId}/bank-confirmation/`, { method: 'POST', body: { date, officer, mode, reference } }),

  addRequest: (fdrId: string, type: 'renewal' | 'release', reason: string, _actorId: string): Promise<unknown> =>
    api(`/fdrs/${fdrId}/requests/`, { method: 'POST', body: { type, reason } }),

  markRead: (notificationId: string): Promise<unknown> =>
    api(`/notifications/${notificationId}/read/`, { method: 'POST' }),

  saveSettings: (settings: AppSettings, _actorId: string): Promise<AppSettings> =>
    api<AppSettings>('/settings/', { method: 'PUT', body: settings })
};
