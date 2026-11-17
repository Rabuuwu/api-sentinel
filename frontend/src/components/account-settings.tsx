import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api,json,setSessionToken} from '@/lib/api';
import {Button} from './ui/button';
type User={id:string;username:string;is_admin:boolean};
export function AccountSettings(){
 const me=useQuery({queryKey:['account'],queryFn:()=>api<User>('/auth/me'),retry:false});
 const users=useQuery({queryKey:['users'],queryFn:()=>api<User[]>('/auth/users'),enabled:!!me.data?.is_admin});
 const [current,setCurrent]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState(''),[invite,setInvite]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const perform=async(action:()=>Promise<void>)=>{setBusy(true);setMessage('');try{await action();}catch(e){setMessage(e instanceof Error?e.message:'Request failed');}finally{setBusy(false);}};
 const signedOut=()=>{setSessionToken('');location.reload();};
 return <article><h2>Account security</h2><p>Signed in as {me.data?.username||'…'}. Each account has its own monitors and notification channels.</p>{me.error&&<p role="alert">Unable to load account.</p>}
 <form onSubmit={e=>{e.preventDefault();if(password!==confirm){setMessage('Passwords do not match');return;}void perform(async()=>{await api('/auth/password',json('POST',{current_password:current,new_password:password}));signedOut();});}}>
 <label>Current password<input type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/></label>
 <label>New password<input type="password" autoComplete="new-password" minLength={15} maxLength={128} required value={password} onChange={e=>setPassword(e.target.value)}/></label>
 <label>Confirm new password<input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
 <Button disabled={busy}>Change password and sign out everywhere</Button></form>
 <Button variant="secondary" disabled={busy} onClick={()=>void perform(async()=>{await api('/auth/logout-all',json('POST'));signedOut();})}>Sign out all sessions</Button>
 {me.data?.is_admin&&<><h3>Invite a user</h3><p>Single-use code, valid for 24 hours. Share it privately.</p><Button disabled={busy} onClick={()=>void perform(async()=>{const result=await api<{invitation:string}>('/auth/invitations',json('POST'));setInvite(result.invitation);})}>Create invitation</Button>{invite&&<label>Invitation code<input readOnly value={invite} onFocus={e=>e.target.select()}/></label>}<h3>Accounts</h3>{users.error&&<p role="alert">Unable to load accounts.</p>}{users.data?.map(user=><p key={user.id}>{user.username} {user.is_admin?'(owner)':''} <Button variant="ghost" disabled={busy} onClick={()=>{if(window.confirm(`Sign out all sessions for ${user.username}?`))void perform(async()=>{await api(`/auth/users/${user.id}/sessions`,json('DELETE'));setMessage('Sessions revoked');if(user.id===me.data?.id)signedOut();});}}>Revoke sessions</Button></p>)}</>}
 {message&&<p role="status">{message}</p>}<p className="field-help">Passwords are hashed using Argon2id. Sessions expire after 8 hours or 30 minutes without requests. Changing a password revokes every session.</p></article>;
}
