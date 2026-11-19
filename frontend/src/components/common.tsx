import type { ReactNode } from 'react';
import { Activity, AlertCircle, ArrowDown, ArrowUp, Check, Inbox, LoaderCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog } from './ui/dialog';
import type { Status, Observation, HistoryInfo } from '@/lib/types';
export const statusLabels:Record<Status,string>={UP:'Operational',DOWN:'Down',DEGRADED:'Degraded',UNKNOWN:'Awaiting data',PAUSED:'Paused'};
export function StatusBadge({status}:{status:Status}){return <span className={`status status-${status}`}><i/>{statusLabels[status]}</span>;}
export function Empty({title,children,action}:{title:string;children?:ReactNode;action?:ReactNode}){return <div className="empty-state"><Inbox size={26}/><h3>{title}</h3><p>{children}</p>{action}</div>;}
export function ErrorState({error,retry}:{error:Error;retry?:()=>void}){return <div className="error-state" role="alert"><AlertCircle size={17}/><span>{error.message}</span>{retry&&<Button size="sm" onClick={retry}>Retry</Button>}</div>;}
export function Skeleton({rows=4}:{rows?:number}){return <div className="skeleton-wrap" role="status" aria-label="Loading data">{Array.from({length:rows},(_,i)=><div key={i} className="skeleton"/>)}</div>;}
export function Metric({label,value,icon,change,help}:{label:string;value:ReactNode;icon?:ReactNode;change?:number|null;help?:string}){return <div className="metric" title={help}><div className="metric-label"><span>{label}</span>{icon||<Activity size={17}/>}</div><div className="metric-value">{value}</div>{change!=null&&<span className={`change ${change>0?'negative':'positive'}`}>{change>0?<ArrowUp size={12}/>:<ArrowDown size={12}/>} {Math.abs(change)}% <span>vs previous period</span></span>}</div>;}
export function Confirm({open,onClose,onConfirm,busy,title,description}:{open:boolean;onClose:()=>void;onConfirm:()=>void;busy:boolean;title:string;description:string}){return <Dialog open={open} onOpenChange={(value)=>{if(!value&&!busy)onClose();}} title={title} description={description}><div className="dialog-actions"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="destructive" disabled={busy} onClick={onConfirm}>{busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}Confirm</Button></div></Dialog>;}

export function ObservationBadge({monitor}:{monitor:Observation & {status:Status}}){
 if(monitor.freshness==='STALE')return <span className="status status-UNKNOWN" title={`Last observed: ${monitor.last_observed_status||monitor.status}`}><i/>No recent measurements</span>;
 return <StatusBadge status={monitor.effective_status||monitor.status}/>;
}
export function HistoryNotice({history}:{history?:HistoryInfo}){
 if(!history)return null;
 return <p className="field-help" role="note">{history.retention_limited&&`Selected period exceeds ${history.retention_days}-day retention. `}{history.completed_checks} completed checks. {history.first_check_at&&history.last_check_at?`Available observations: ${new Date(history.first_check_at).toLocaleString()} – ${new Date(history.last_check_at).toLocaleString()}.`:'No measurements in this period.'} Gaps are unknown; success rate measures checks, not elapsed uptime.</p>;
}
