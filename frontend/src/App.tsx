import { Component,useState,type ReactNode } from 'react';
import { Navigate,Route,Routes,useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight,LoaderCircle,ShieldCheck } from 'lucide-react';
import { api,apiBase,setApiKey } from './lib/api';
import type { System } from './lib/types';
import { Button } from './components/ui/button';
import { Shell } from './components/shell';
import { Overview } from './pages/overview';
import { MonitorDetails } from './pages/monitor-details';
import { Incidents } from './pages/incidents';
import { Notifications } from './pages/notifications';
import { StatusPages } from './pages/status-pages';
import { PublicStatus } from './pages/public-status';
import { Settings } from './pages/settings';
class ErrorBoundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<div className="fatal-error"><h1>This view could not be displayed.</h1><p>Your monitoring worker continues independently.</p><Button onClick={()=>location.reload()}>Reload dashboard</Button></div>:this.props.children;}}
export function App(){const [authenticated,setAuthenticated]=useState(false),[key,setKey]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);const client=useQueryClient(),location=useLocation();
 if(location.pathname.startsWith('/status/'))return <ErrorBoundary><Routes><Route path="/status/:slug" element={<PublicStatus/>}/></Routes></ErrorBoundary>;
 if(!authenticated)return <main className="login-page"><div className="login-brand"><span className="brand-symbol"><ShieldCheck size={24}/></span><span>API Sentinel</span><span className="subtle-tag">Self-hosted</span></div><section className="login-panel"><p className="login-eyebrow">Your monitoring workspace</p><h1>Every service.<br/>In sight.</h1><p className="login-description">Availability, response times and incidents.<br/>All on infrastructure you control.</p><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setApiKey(key.trim());try{const system=await api<System>('/system',{signal:AbortSignal.timeout(120000)});client.setQueryData(['system'],system);setAuthenticated(true);setKey('');}catch(error){setApiKey('');setError(error instanceof Error?error.message:'Unable to connect');}finally{setBusy(false);}}}><p className="field-help">Connected API: <span className="mono">{apiBase}</span></p><label>Workspace API key<input type="password" autoComplete="off" required value={key} onChange={e=>setKey(e.target.value)} placeholder="Enter SENTINEL_API_KEY"/></label>{error&&<p className="form-error" role="alert">{error}</p>}{busy&&<p className="field-help" role="status">Connecting. A sleeping server may take up to two minutes to start.</p>}<Button variant="default" disabled={busy}>{busy?<LoaderCircle size={16} className="spin"/>:<ArrowRight size={16}/>}Open workspace</Button></form><p className="field-help">Use SENTINEL_API_KEY from your server environment.<br/>Your key stays in memory and is cleared when this tab reloads.</p></section><footer>Private workspace. No tracking. Your services.</footer></main>;
 const logout=()=>{setApiKey('');void client.cancelQueries();client.clear();setAuthenticated(false);};
 return <ErrorBoundary><Routes><Route element={<Shell onLogout={logout}/>}><Route index element={<Overview/>}/><Route path="monitors" element={<Overview/>}/><Route path="monitors/:id" element={<MonitorDetails/>}/><Route path="incidents" element={<Incidents/>}/><Route path="notifications" element={<Notifications/>}/><Route path="status-pages" element={<StatusPages/>}/><Route path="settings" element={<Settings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Route></Routes></ErrorBoundary>;
}
