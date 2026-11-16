import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Activity, Bell, ChevronRight, CircleAlert, Globe2, LayoutDashboard, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Settings, ShieldCheck, X } from 'lucide-react';
import { useMonitors,useSystem } from '@/lib/queries';
import type { Monitor,TimeWindow } from '@/lib/types';
import { Button } from './ui/button';
import { MonitorEditor } from './monitor-editor';
export interface ShellContext {window:TimeWindow;openEditor:(monitor?:Monitor)=>void;}
const links=[['/','Overview',LayoutDashboard],['/monitors','Monitors',Activity],['/status-pages','Status pages',Globe2],['/notifications','Notifications',Bell],['/incidents','Incidents',CircleAlert],['/settings','Settings',Settings]] as const;
export function Shell({onLogout}:{onLogout:()=>void}){
 const [collapsed,setCollapsed]=useState(false),[mobile,setMobile]=useState(false),[window,setWindow]=useState<TimeWindow>('24h');const [editor,setEditor]=useState<Monitor|null|undefined>(undefined);
 const monitors=useMonitors(),system=useSystem(),client=useQueryClient(),location=useLocation();
 const current=monitors.data?.find(m=>location.pathname===`/monitors/${m.id}`);const section=links.find(([path])=>path!=='/'&&location.pathname.startsWith(path))?.[1]||'Overview';
 return <div className={`app-shell ${collapsed?'collapsed':''} ${mobile?'mobile-open':''}`}>
 <button className="sidebar-scrim" aria-label="Close navigation" onClick={()=>setMobile(false)}/>
 <aside className="sidebar"><div className="brand-row"><NavLink to="/" className="brand"><span className="brand-symbol"><ShieldCheck size={22}/></span><span>API Sentinel</span></NavLink><Button size="icon" variant="ghost" onClick={()=>setCollapsed(!collapsed)} aria-label={collapsed?'Expand sidebar':'Collapse sidebar'}>{collapsed?<PanelLeftOpen size={17}/>:<PanelLeftClose size={17}/>}</Button><Button className="mobile-close" size="icon" variant="ghost" aria-label="Close menu" onClick={()=>setMobile(false)}><X size={18}/></Button></div>
 <div className="nav-caption">Workspace</div><nav aria-label="Workspace">{links.map(([path,label,Icon])=><NavLink key={path} to={path} end={path==='/'||path==='/monitors'} title={label} onClick={()=>setMobile(false)} className={({isActive})=>`nav-link ${isActive?'active':''}`}><Icon size={17}/><span>{label}</span>{label==='Incidents'&&system.data?.failed_alerts?<b className="nav-count">!</b>:null}</NavLink>)}</nav>
 <div className="nav-caption monitor-caption"><span>Monitors</span><Button size="icon" variant="ghost" aria-label="Add monitor" onClick={()=>setEditor(null)}><Plus size={16}/></Button></div>
 <div className="sidebar-monitors">{monitors.data?.map(m=><NavLink key={m.id} to={`/monitors/${m.id}`} title={m.name} className={({isActive})=>`monitor-link ${isActive?'active':''}`} onClick={()=>setMobile(false)}><i className={`dot dot-${m.status}`}/><span>{m.name}</span></NavLink>)}{monitors.isPending&&<span className="sidebar-note">Loading monitors…</span>}{monitors.isError&&<span className="sidebar-note">Unable to load monitors</span>}{monitors.data?.length===0&&<span className="sidebar-note">Your first monitor starts here.</span>}</div>
 <div className="sidebar-bottom"><div className="worker-indicator"><i className={`dot ${!system.isError&&system.data?.worker_alive?'dot-UP':'dot-UNKNOWN'}`}/><span>{system.isError?'System unreachable':system.data?.worker_alive?'Worker connected':'Worker not reporting'}</span></div><div className="sidebar-meta"><span>Self-hosted</span><span>v{system.data?.version||'0.2.0'}</span></div><Button variant="ghost" onClick={onLogout} title="Lock workspace"><LogOut size={16}/><span>Lock workspace</span></Button></div>
 </aside>
 <div className="app-body"><header className="topbar"><Button className="mobile-menu" size="icon" variant="ghost" aria-label="Open navigation" onClick={()=>setMobile(true)}><Menu size={19}/></Button><div className="breadcrumbs"><Activity size={16}/><span>{section}</span>{current&&<><ChevronRight size={15}/><i className={`dot dot-${current.status}`}/><span className="crumb-name">{current.name}</span><ChevronRight size={15}/><span>Overview</span></>}</div><div className="topbar-actions"><span className="location-label">Self-hosted</span><select aria-label="Time range" value={window} onChange={e=>setWindow(e.target.value as TimeWindow)}><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option></select><Button size="icon" variant="ghost" aria-label="Refresh data" onClick={()=>void client.invalidateQueries()}><RefreshCw size={17}/></Button></div></header>
 <main id="main-content"><Outlet context={{window,openEditor:(m?:Monitor)=>setEditor(m||null)} satisfies ShellContext}/></main><footer className="app-footer"><span>API Sentinel <span className="muted">/</span> Your infrastructure. Your data.</span><span>Live views refresh every 30s · Measurements from this host</span></footer></div>
 {editor!==undefined&&<MonitorEditor monitor={editor} onClose={()=>setEditor(undefined)}/>}
 </div>;
}
