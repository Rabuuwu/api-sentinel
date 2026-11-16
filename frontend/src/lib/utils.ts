import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { format, formatDistanceToNowStrict } from 'date-fns';
export function cn(...values:ClassValue[]) { return twMerge(clsx(values)); }
export const ms=(v:number|null|undefined)=>v==null?'—':`${Math.round(v).toLocaleString()} ms`;
export const percent=(v:number|null|undefined)=>v==null?'No data':`${v.toFixed(2)}%`;
export const date=(v:string|null|undefined)=>v?format(new Date(v),'MMM d, yyyy · HH:mm:ss'):'No measurements';
export const relative=(v:string|null)=>v?formatDistanceToNowStrict(new Date(v),{addSuffix:true}):'Not checked yet';
export const duration=(seconds:number)=>seconds<60?`${Math.round(seconds)}s`:seconds<3600?`${Math.floor(seconds/60)}m ${Math.floor(seconds%60)}s`:`${Math.floor(seconds/3600)}h ${Math.floor(seconds%3600/60)}m`;
export function delta(now:number|null, previous:number|null|undefined) { return now==null||previous==null||previous===0?null:Math.round((now-previous)/previous*100); }
