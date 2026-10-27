import type { Institution } from '../types';
import { api } from './http';

export type InstitutionInput = Pick<Institution, 'code' | 'name' | 'state' | 'contactName' | 'email' | 'phone'>;

export const institutionApi = {
  list: (): Promise<Institution[]> => api<Institution[]>('/institutions/'),
  /** Create (no id) or edit (with id). The server checks that the caller is an administrator. */
  save(input: InstitutionInput, _actorId: string, _actorRole: string, id?: string): Promise<Institution> {
    if (id) return api<Institution>(`/institutions/${id}/`, { method: 'PATCH', body: input });
    return api<Institution>('/institutions/', { method: 'POST', body: input });
  },
  /** Deactivates rather than deletes, so history is preserved. */
  deactivate(id: string, _actorId: string, _actorRole: string): Promise<Institution> {
    return api<Institution>(`/institutions/${id}/`, { method: 'PATCH', body: { status: 'Inactive' } });
  }
};
