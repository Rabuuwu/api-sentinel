import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {ShieldCheck, LoaderCircle} from 'lucide-react';
import {api, apiBase, json, setSessionToken} from '@/lib/api';
import {EmailFlow} from './email-flow';
import {Button} from './ui/button';
export function SignIn({onSignedIn}:{onSignedIn:()=>void}){
 const setup=useQuery({queryKey:['auth-setup'],queryFn:()=>api<{setup_required:boolean;mail_enabled?:boolean}>('/auth/setup',{signal:AbortSignal.timeout(120000)},true),retry:false});
 const [register,setRegister]=useState(false),[username,setUsername]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState(''),[code,setCode]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [email,setEmail]=useState(''),[notice,setNotice]=useState(''),[mailMode,setMailMode]=useState<'forgot'|'resend'|null>(null);
 const bootstrap=setup.data?.setup_required,creating=bootstrap||register;
 if(mailMode)return <EmailFlow mode={mailMode} onBack={()=>setMailMode(null)}/>;
 return <main className="login-page"><div className="login-brand"><span className="brand-symbol"><ShieldCheck size={24}/></span><span>API Sentinel</span></div><section className="login-panel"><p className="login-eyebrow">Your private monitoring workspace</p><h1>{bootstrap?'Create owner account':register?'Create your account':'Welcome back.'}</h1><p className="login-description">Your services, history and notifications.<br/>Accessible only through your account.</p>
 {setup.isPending?<p role="status">Connecting to server…</p>:setup.error?<><p role="alert">Cannot reach the API. Check its address and try again.</p><Button onClick={()=>void setup.refetch()}>Retry</Button></>:<form onSubmit={async e=>{e.preventDefault();setError('');if(creating&&password!==confirm){setError('Passwords do not match');return;}setBusy(true);try{const path=bootstrap?'bootstrap':register?'register':'login';const data={username,password,...(creating&&setup.data?.mail_enabled?{email}:{}),...(bootstrap?{setup_key:code}:register?{invitation:code}:{})};const result=await api<{token?:string;verification_required?:boolean;message?:string}>(`/auth/${path}`,{...json('POST',data),signal:AbortSignal.timeout(120000)},true);setPassword('');setCode('');if(result.verification_required){setNotice(result.message||'Check your email');setRegister(false);void setup.refetch();}else if(result.token){setSessionToken(result.token);onSignedIn();}}catch(error){setError(error instanceof Error?error.message:'Sign-in failed');}finally{setBusy(false);}}}>
 {notice&&<p role="status">{notice}</p>}
 {creating&&setup.data?.mail_enabled&&<label>Email address<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label>}
 <label>Username<input autoComplete="username" required minLength={3} maxLength={40} pattern="[a-zA-Z0-9_.\-]+" value={username} onChange={e=>setUsername(e.target.value)}/></label>
 <label>Password<input type="password" autoComplete={creating?'new-password':'current-password'} required minLength={15} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label>
 {creating&&<><p className="field-help">Use a unique passphrase of 15–128 characters.</p><label>Confirm password<input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label><label>{bootstrap?'Owner setup key':'Invitation code'}<input type="password" autoComplete="off" required value={code} onChange={e=>setCode(e.target.value)}/></label><p className="field-help">{bootstrap?'Use SENTINEL_API_KEY from Render once to claim existing monitors. Afterwards sign in with your username and password.':'Ask the server owner for a single-use invitation.'}</p></>}
 {error&&<p className="form-error" role="alert">{error}</p>}<Button disabled={busy}>{busy?<LoaderCircle className="spin" size={16}/>:null}{creating?'Create account':'Sign in'}</Button>
 {!bootstrap&&<Button type="button" variant="ghost" disabled={busy} onClick={()=>{setRegister(!register);setError('');setPassword('');setConfirm('');setCode('');}}>{register?'Back to sign in':'I have an invitation'}</Button>}
 </form>}
 {setup.data?.mail_enabled&&<div><Button variant="ghost" onClick={()=>setMailMode('forgot')}>Forgot password?</Button><Button variant="ghost" onClick={()=>setMailMode('resend')}>Resend confirmation</Button></div>}
 <p className="field-help">API: <span className="mono">{apiBase}</span><br/>Sessions stay in this tab only. Reloading requires sign-in.</p></section><footer>Private workspace. No tracking.</footer></main>;
}
