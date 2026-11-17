import { Component,useState,useEffect,useCallback,type ReactNode } from 'react';
import { Navigate,Route,Routes,useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api,setSessionToken,onSessionExpired } from './lib/api';
import { SignIn } from './components/sign-in';
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
export function App(){
 const [authenticated,setAuthenticated]=useState(false);const client=useQueryClient(),location=useLocation();
 const clear=useCallback(()=>{setSessionToken('');void client.cancelQueries();client.clear();setAuthenticated(false);},[client]);
 useEffect(()=>{onSessionExpired(clear);return()=>onSessionExpired(()=>{});},[clear]);
 const logout=async()=>{try{await api('/auth/logout',{method:'POST'});}finally{clear();}};
 if(location.pathname.startsWith('/status/'))return <ErrorBoundary><Routes><Route path="/status/:slug" element={<PublicStatus/>}/></Routes></ErrorBoundary>;
 if(!authenticated)return <SignIn onSignedIn={()=>setAuthenticated(true)}/>;
 return <ErrorBoundary><Routes><Route element={<Shell onLogout={()=>void logout().catch(()=>{})}/>}><Route index element={<Overview/>}/><Route path="monitors" element={<Overview/>}/><Route path="monitors/:id" element={<MonitorDetails/>}/><Route path="incidents" element={<Incidents/>}/><Route path="notifications" element={<Notifications/>}/><Route path="status-pages" element={<StatusPages/>}/><Route path="settings" element={<Settings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Route></Routes></ErrorBoundary>;
}
