import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { LoaderCircle } from 'lucide-react';
import { api, json } from '@/lib/api';
import { useChannels } from '@/lib/queries';
import type { Monitor, MonitorInput } from '@/lib/types';
import { Dialog } from './ui/dialog';
import { Button } from './ui/button';
import { ErrorState } from './common';
export const defaults:MonitorInput={name:'',description:'',url:'',method:'GET',interval_seconds:300,timeout_seconds:20,expected_status_min:200,expected_status_max:299,failure_threshold:3,recovery_threshold:2,degraded_latency_ms:null,degraded_threshold:3,notification_channel_ids:[]};
export function validateMonitor(value:MonitorInput):string|null {
  if(!value.name.trim())return 'Enter a monitor name.';
  try{const url=new URL(value.url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||!['','80','443'].includes(url.port))return 'Use a public HTTP(S) URL, ports 80/443, without credentials or query parameters.';}catch{return 'Enter a valid HTTP(S) URL.';}
  if(value.interval_seconds<60||value.interval_seconds>86400)return 'Interval must be between 60 and 86400 seconds.';
  if(value.timeout_seconds<2||value.timeout_seconds>30)return 'Timeout must be between 2 and 30 seconds.';
  if(value.expected_status_min>value.expected_status_max)return 'The minimum HTTP status cannot exceed the maximum.';
  return null;
}
export function MonitorEditor({monitor,onClose}:{monitor:Monitor|null;onClose:()=>void}){
 const [value,setValue]=useState<MonitorInput>(()=>monitor?Object.fromEntries(Object.keys(defaults).map(k=>[k,monitor[k as keyof MonitorInput]])) as unknown as MonitorInput:{...defaults});
 const [validation,setValidation]=useState<string|null>(null);const channels=useChannels();const client=useQueryClient();
 const mutation=useMutation({mutationFn:()=>api<Monitor>(monitor?`/monitors/${monitor.id}`:'/monitors',json(monitor?'PATCH':'POST',value)),onSuccess:()=>{void client.invalidateQueries();toast.success(monitor?'Monitor updated':'Monitor created');onClose();}});
 const update=<K extends keyof MonitorInput>(key:K,next:MonitorInput[K])=>setValue(old=>({...old,[key]:next}));
 const number=(key:keyof MonitorInput,label:string,min:number,max:number)=><label>{label}<input type="number" min={min} max={max} required value={value[key] as number} onChange={e=>update(key,Number(e.target.value) as never)}/></label>;
 return <Dialog open onOpenChange={v=>{if(!v&&!mutation.isPending)onClose();}} title={monitor?'Configure monitor':'New monitor'} description="Check a public endpoint from your self-hosted worker."><form onSubmit={e=>{e.preventDefault();const error=validateMonitor(value);setValidation(error);if(!error)mutation.mutate();}}>
 <label>Name<input autoFocus required maxLength={120} value={value.name} onChange={e=>update('name',e.target.value)} placeholder="DnD Companion API"/></label>
 <label>URL<input type="url" required maxLength={2048} value={value.url} onChange={e=>update('url',e.target.value)} placeholder="https://dndcompanion-api.onrender.com/ready"/></label>
 <p className="field-help">Public HTTP(S) only. Private networks, redirects and credentials are blocked by the worker.</p>
 <label>Description<textarea maxLength={1000} value={value.description} onChange={e=>update('description',e.target.value)} placeholder="What does this monitor check?"/></label>
 <div className="form-grid"><label>Method<select value={value.method} onChange={e=>update('method',e.target.value as 'GET'|'HEAD')}><option>GET</option><option>HEAD</option></select></label>{number('interval_seconds','Check interval (seconds)',60,86400)}{number('timeout_seconds','Timeout (seconds)',2,30)}{number('failure_threshold','Failures to open an incident',1,100)}{number('recovery_threshold','Healthy checks to recover',1,100)}{number('expected_status_min','Expected HTTP from',100,599)}{number('expected_status_max','Expected HTTP to',100,599)}
 <label>Degraded above (ms)<input type="number" min={1} max={30000} value={value.degraded_latency_ms??''} placeholder="Disabled" onChange={e=>update('degraded_latency_ms',e.target.value===''?null:Number(e.target.value))}/></label>{number('degraded_threshold','Slow checks to degrade',1,100)}</div>
 <fieldset><legend>Notification channels</legend>{channels.data&&value.notification_channel_ids.some(id=>!channels.data?.some(c=>c.id===id))&&<p className="field-help">Some assigned channels have been removed. <Button type="button" size="sm" onClick={()=>update('notification_channel_ids',value.notification_channel_ids.filter(id=>channels.data!.some(c=>c.id===id)))}>Clear unavailable assignments</Button> An empty selection uses the environment default.</p>}{channels.isPending?<p className="muted">Loading channels…</p>:channels.error?<ErrorState error={channels.error} retry={()=>void channels.refetch()}/>:channels.data?.length?channels.data.map(channel=><label className="checkbox" key={channel.id}><input type="checkbox" checked={value.notification_channel_ids.includes(channel.id)} onChange={e=>update('notification_channel_ids',e.target.checked?[...value.notification_channel_ids,channel.id]:value.notification_channel_ids.filter(id=>id!==channel.id))}/>{channel.name}{!channel.enabled&&' (disabled)'}</label>):<p className="field-help">No channels configured. Add Discord in Notifications.</p>}<p className="field-help">No selection uses the environment default (Discord or console).</p></fieldset>
 {validation&&<p className="form-error" role="alert">{validation}</p>}{mutation.error&&<ErrorState error={mutation.error}/>}
 <div className="dialog-actions"><Button type="button" onClick={onClose} disabled={mutation.isPending}>Cancel</Button><Button variant="default" disabled={mutation.isPending}>{mutation.isPending&&<LoaderCircle className="spin" size={15}/>}Save monitor</Button></div>
 </form></Dialog>;
}
