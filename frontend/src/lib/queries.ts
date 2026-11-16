import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { Channel, Monitor, Page, System } from './types';
export const useSystem=()=>useQuery({queryKey:['system'],queryFn:({signal})=>api<System>('/system',{signal}),refetchInterval:30000});
export const useChannels=()=>useQuery({queryKey:['channels'],queryFn:({signal})=>api<Channel[]>('/notifications',{signal})});
export const useMonitors=()=>useQuery({queryKey:['monitors'],queryFn:async({signal})=>{
  const items:Monitor[]=[];let cursor:string|null=null;
  do {const data:Page<Monitor>=await api(`/monitors?limit=100${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`,{signal});items.push(...data.items);cursor=data.next_cursor;}while(cursor);
  return items;
},refetchInterval:60000});
