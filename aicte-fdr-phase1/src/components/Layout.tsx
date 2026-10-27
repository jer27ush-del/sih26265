import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Building2, LayoutDashboard, FileText, ShieldCheck, Bell, ClipboardList, Settings, LogOut, Landmark, ChevronRight } from 'lucide-react';
import { useAuth } from '../useAuth';
import { can } from '../domain/permissions';
import { formatRole } from '../utils/format';
const nav = [
 {label:'Dashboard',to:'/dashboard',icon:LayoutDashboard,action:null},
 {label:'Institutions',to:'/institutions',icon:Building2,action:'manage_institutions' as const},
 {label:'All FDRs',to:'/fdrs',icon:FileText,action:'view_fdrs' as const},
 {label:'Register FDR / Bulk Import',to:'/register',icon:Landmark,action:'register_fdr' as const},
 {label:'Verification',to:'/verification',icon:ShieldCheck,action:'review_fdr' as const},
 {label:'Maturity & Renewal',to:'/maturity',icon:Bell,action:'view_fdrs' as const},
 {label:'Release Requests',to:'/release',icon:ClipboardList,action:'submit_request' as const},
 {label:'Reports',to:'/reports',icon:FileText,action:'view_reports' as const},
 {label:'Notifications',to:'/notifications',icon:Bell,action:null},
 {label:'Audit Logs',to:'/audit',icon:ClipboardList,action:'view_audit_logs' as const},
 {label:'Settings & Profile',to:'/settings',icon:Settings,action:null}
];
export function Layout() {
 const {user,logout,switchRole,demoUsers} = useAuth(); const navigate = useNavigate();
 if (!user) return null;
 return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark"><Landmark size={23}/></div><div><strong>AICTE FDR</strong><span>Management Portal</span></div></div><div className="sidebar-label">FDR DESK</div><nav aria-label="Main navigation">{nav.filter((item) => !item.action || can(user.role,item.action) || (item.to === '/audit' && user.role === 'scrutiny_officer')).map((item) => <NavLink key={item.to} to={item.to} className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={18} aria-hidden="true"/><span>{item.label}</span>{item.to === '/institutions' && <ChevronRight size={14}/>}</NavLink>)}</nav><div className="sidebar-footer"><div className="avatar">{user.name.split(' ').map((part) => part[0]).slice(0,2).join('')}</div><div className="user-mini"><strong>{user.name}</strong><span>{formatRole(user.role)}</span></div><button className="icon-button" aria-label="Sign out" onClick={() => {logout();navigate('/login');}}><LogOut size={17}/></button></div></aside><main className="main-area"><header className="topbar"><div><span className="eyebrow">GOVERNMENT OF INDIA</span><strong>All India Council for Technical Education</strong></div><div className="topbar-right"><span className="environment-tag">DEMO ENVIRONMENT</span><label className="role-switch-label">DEMO: switch role<select aria-label="DEMO: switch role" value={user.id} onChange={(event)=>switchRole(event.target.value)}>{demoUsers.map((demoUser)=><option key={demoUser.id} value={demoUser.id}>{formatRole(demoUser.role)}</option>)}</select></label><span className="top-user">{user.name}</span></div></header><div className="page-content"><Outlet/></div><footer className="page-footer">AICTE FDR Management Portal <span>Prototype · Fictional demonstration data only</span></footer></main></div>;
}
