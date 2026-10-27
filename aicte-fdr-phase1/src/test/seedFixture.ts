import type { AppStore } from '../types';
const now = new Date().toISOString();
export const seedStore: AppStore = {
 institutions: [
  { id:'inst-001', code:'DEMO001', name:'Demo Engineering College', state:'Tamil Nadu', contactName:'Priya Sample', email:'demo@example.com', phone:'+91 90000 10001', status:'Active', createdAt:now, updatedAt:now },
  { id:'inst-002', code:'DEMO002', name:'Sample Institute of Technology', state:'Karnataka', contactName:'Arun Demo', email:'sample@example.com', phone:'+91 90000 10002', status:'Active', createdAt:now, updatedAt:now },
  { id:'inst-003', code:'DEMO003', name:'Fictional Polytechnic College', state:'Telangana', contactName:'Meera Example', email:'poly@example.com', phone:'+91 90000 10003', status:'Inactive', createdAt:now, updatedAt:now }
 ],
 users: [
  { id:'user-inst', name:'Demo Institution User', email:'institution@demo.test', role:'institution_user', institutionId:'inst-001', status:'Active', lastLogin:null },
  { id:'user-officer', name:'Sample Scrutiny Officer', email:'officer@demo.test', role:'scrutiny_officer', institutionId:null, status:'Active', lastLogin:null },
  { id:'user-admin', name:'Demo Administrator', email:'admin@demo.test', role:'administrator', institutionId:null, status:'Active', lastLogin:null },
  { id:'user-auditor', name:'Sample Auditor', email:'auditor@demo.test', role:'auditor', institutionId:null, status:'Active', lastLogin:null }
 ], fdrs:[
  {id:'fdr-demo-1001',fdrNumber:'DEMO-FDR-1001',institutionId:'inst-001',bank:'Sample National Bank',branch:'Chennai Main',amountPaise:50000000,issueDate:'2026-01-15',maturityDate:'2027-01-15',interestRate:6.5,payoutType:'cumulative',category:'Security Deposit',lienMarked:true,heldInFavourOfAICTE:true,status:'Active',parentFdrId:null,reviewFlag:false,createdAt:now,updatedAt:now},
  {id:'fdr-demo-1002',fdrNumber:'DEMO-FDR-1002',institutionId:'inst-002',bank:'Demo State Bank',branch:'Bengaluru Central',amountPaise:25000000,issueDate:'2025-08-01',maturityDate:'2026-11-15',interestRate:6.25,payoutType:'periodic',category:'Security Deposit',lienMarked:true,heldInFavourOfAICTE:true,status:'Under Verification',parentFdrId:null,reviewFlag:true,createdAt:now,updatedAt:now},
  {id:'fdr-demo-1003',fdrNumber:'DEMO-FDR-1003',institutionId:'inst-001',bank:'Sample National Bank',branch:'Adambakkam',amountPaise:12500000,issueDate:'2024-12-01',maturityDate:'2026-12-01',interestRate:6.75,payoutType:'cumulative',category:'Performance Guarantee',lienMarked:false,heldInFavourOfAICTE:true,status:'Nearing Maturity',parentFdrId:null,reviewFlag:false,createdAt:now,updatedAt:now}
 ], documents:[{id:'doc-demo-1',fdrId:'fdr-demo-1001',fileName:'DEMO-FDR-1001-sample.pdf',mimeType:'application/pdf',sizeBytes:245760,version:1,uploadedBy:'user-inst',uploadedAt:now,active:true}], verifications:[], queries:[], requests:[], notifications:[{id:'notification-demo-1',userId:'user-inst',type:'maturity',message:'DEMO-FDR-1001 maturity reminder: review the upcoming maturity date.',link:'/maturity',readAt:null,sentAt:now}], auditLogs:[],
 settings: { maturityThresholds:[90,60,30], escalationContacts:['senior.officer@demo.test'], documentMaxBytes:10485760, allowedDocumentTypes:['application/pdf','image/png','image/jpeg'], banks:['Sample National Bank','Demo State Bank','Example Cooperative Bank'], categories:['Security Deposit','Performance Guarantee','Other'], minimumTenureDays:365, amountLimitsPaise:{min:100,max:100000000000} }
};
