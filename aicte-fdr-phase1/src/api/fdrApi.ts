import type { FDR } from '../types';
import { api } from './http';

/** The server returns only the FDRs this user may see (institution users see their own institution only). */
export const fdrApi = {
  list: (): Promise<FDR[]> => api<FDR[]>('/fdrs/'),
  get: (id: string): Promise<FDR> => api<FDR>(`/fdrs/${id}/`)
};
