let sessionToken='';
let expired=()=>{};
export function onSessionExpired(callback:()=>void){expired=callback;}
export function setSessionToken(value:string){sessionToken=value;}
export class ApiError extends Error { constructor(message:string, public status:number){super(message);} }
export const apiBase=(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/,'');
export async function api<T>(path:string, options:RequestInit={}, publicRequest=false):Promise<T> {
  const headers = new Headers(options.headers);
  if(!publicRequest) headers.set('Authorization',`Bearer ${sessionToken}`);
  if(options.body) headers.set('Content-Type','application/json');
  let response:Response;
  try { response=await fetch(`${apiBase}${path}`,{...options,headers,credentials:'omit',redirect:'error',signal:options.signal || AbortSignal.timeout(20000)}); }
  catch(error) { if(options.signal?.aborted) throw error; throw new ApiError('Cannot reach API Sentinel. Check that the server is running and its HTTPS address and CORS settings are correct.',0); }
  if(!response.ok){if(response.status===401&&!publicRequest)expired();const body=await response.json().catch(()=>({}));throw new ApiError(body.error?.message || `Request failed (${response.status})`,response.status);}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}
export const json=(method:string,body?:unknown):RequestInit=>({method,...(body===undefined?{}:{body:JSON.stringify(body)})});
