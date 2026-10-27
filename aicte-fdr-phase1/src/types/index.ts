export type Role = 'institution_user' | 'scrutiny_officer' | 'administrator' | 'auditor';
export type RecordStatus = 'Active' | 'Inactive';
export type FDRStatus = 'Submitted' | 'Under Verification' | 'Query Raised' | 'Corrected' | 'Verified' | 'Active' | 'Nearing Maturity' | 'Matured' | 'Renewed' | 'Release Requested' | 'Released / Closed' | 'Rejected';
export interface Institution { id: string; code: string; name: string; state: string; contactName: string; email: string; phone: string; status: RecordStatus; createdAt: string; updatedAt: string }
export interface User { id: string; name: string; email: string; role: Role; institutionId: string | null; status: RecordStatus; lastLogin: string | null }
export interface Document { id: string; fdrId: string; fileName: string; mimeType: string; sizeBytes: number; version: number; uploadedBy: string; uploadedAt: string; active: boolean }
export interface FDR { id: string; fdrNumber: string; institutionId: string; bank: string; branch: string; amountPaise: number; issueDate: string; maturityDate: string; interestRate: number; payoutType: 'cumulative' | 'periodic'; category: string; lienMarked: boolean; heldInFavourOfAICTE: boolean; status: FDRStatus; parentFdrId: string | null; reviewFlag: boolean; createdAt: string; updatedAt: string }
export interface Verification { id: string; fdrId: string; ruleResults: Record<string, 'pass' | 'warning' | 'fail'>; officerId: string | null; bankConfirmedOn: string | null; bankReference: string | null; decision: 'Verified' | 'Rejected' | null; reason: string | null }
export interface Query { id: string; fdrId: string; raisedBy: string; message: string; reply: string | null; status: 'open' | 'resolved'; raisedAt: string; resolvedAt: string | null }
export interface Request { id: string; fdrId: string; type: 'renewal' | 'release'; reason: string; status: string; submittedBy: string; recommendedBy: string | null; decidedBy: string | null }
export interface Notification { id: string; userId: string; type: string; message: string; link: string; readAt: string | null; sentAt: string }
export interface AuditLog { id: string; actorId: string; action: string; entity: string; entityId: string; oldValue: unknown; newValue: unknown; ip: string; timestamp: string }
export interface AppSettings { maturityThresholds: number[]; escalationContacts: string[]; documentMaxBytes: number; allowedDocumentTypes: string[]; banks: string[]; categories: string[]; minimumTenureDays: number; amountLimitsPaise: { min: number; max: number } }
export interface AppStore { institutions: Institution[]; users: User[]; fdrs: FDR[]; documents: Document[]; verifications: Verification[]; queries: Query[]; requests: Request[]; notifications: Notification[]; auditLogs: AuditLog[]; settings: AppSettings }
export interface Session { userId: string }
