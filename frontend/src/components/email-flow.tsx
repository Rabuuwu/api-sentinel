import {useEffect,useState} from 'react';
import {api,json} from '@/lib/api';
import {Button} from './ui/button';
export function EmailFlow({mode,onBack}:{mode:'forgot'|'resend'|'link';onBack?:()=>void}){
 const [initial]=useState(()=>new URLSearchParams(window.location.hash.split('?')[1]||''));
 const [token,setToken]=useState(initial.get('token')||''),purpose=initial.get('purpose');
 const [email,setEmail]=useState(''),[username,setUsername]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[done,setDone]=useState(false);
 useEffect(()=>{if(mode==='link')window.history.replaceState(null,'',window.location.pathname+window.location.search+'#/account-link');},[mode]);
 const reset=mode==='link'&&purpose==='reset';
 const back=()=>{if(onBack)onBack();else window.location.assign(window.location.pathname+window.location.search);};
 return <main className="login-page"><section className="login-panel"><p className="login-eyebrow">API Sentinel</p><h1>{mode==='forgot'?'Forgot your password?':mode==='resend'?'Resend confirmation':reset?'Choose a new password':'Confirm your email'}</h1>
 <p className="field-help">{mode==='forgot'?'Enter the verified email address saved on your account.':mode==='resend'?'Enter your username and the address awaiting confirmation.':'Continue only if you requested this action. Opening this page does not consume the link.'}</p>
 {!done&&<form onSubmit={async e=>{e.preventDefault();setError('');if(reset&&password!==confirm){setError('Passwords do not match');return;}if(mode==='link'&&(!token||!['verify','reset'].includes(purpose||''))){setError('Invalid link. Request a new email.');return;}setBusy(true);try{const path=mode==='forgot'?'/auth/password-reset/request':mode==='resend'?'/auth/email/resend':reset?'/auth/password-reset/confirm':'/auth/email/verify';const body=mode==='forgot'?{email}:mode==='resend'?{email,username}:reset?{token,new_password:password}:{token};const result=await api<{message:string}>(path,{...json('POST',body),signal:AbortSignal.timeout(120000)},true);setMessage(result.message);setToken('');setPassword('');setConfirm('');setDone(true);}catch(e){setError(e instanceof Error?e.message:'Request failed');}finally{setBusy(false);}}}>
 {mode==='resend'&&<label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label>}
 {mode!=='link'&&<label>Email address<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label>}
 {reset&&<><label>New password<input type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><label>Confirm new password<input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label></>}
 <Button disabled={busy}>{busy?'Please wait…':mode==='link'?(reset?'Set new password':'Confirm email'):'Send email'}</Button></form>}
 {error&&<p role="alert" className="form-error">{error}</p>}{message&&<p role="status">{message}</p>}<Button variant="ghost" onClick={back}>Back to sign in</Button></section></main>;
}
