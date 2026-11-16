let apiKey='';
export function setApiKey(value:string){apiKey=value;}
export class ApiError extends Error { constructor(message:string, public status:number){super(message);} }
const base=import.meta.env.VITE_API_BASE_URL || '/api/v1';
export async function api<T>(path:string, options:RequestInit={}, publicRequest=false):Promise<T> {
  const headers = new Headers(options.headers);
  if(!publicRequest) headers.set('X-API-Key',apiKey);
  if(options.body) headers.set('Content-Type','application/json');
  let response:Response;
  try { response=await fetch(`${base}${path}`,{...options,headers,signal:options.signal || AbortSignal.timeout(20000)}); }
  catch(error) { if(options.signal?.aborted) throw error; throw new ApiError('Cannot reach API Sentinel. Check the server and retry.',0); }
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new ApiError(body.error?.message || `Request failed (${response.status})`,response.status);}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}
export const json=(method:string,body?:unknown):RequestInit=>({method,...(body===undefined?{}:{body:JSON.stringify(body)})});
