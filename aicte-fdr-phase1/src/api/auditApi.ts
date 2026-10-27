import type { AuditLog, Role } from '../types';
import { api } from './http';

/** Read-only. Entries are written by the server inside the same transaction as the change they describe. */
export const auditApi = {
  list: (_role?: Role): Promise<AuditLog[]> => api<AuditLog[]>('/audit-logs/')
};
