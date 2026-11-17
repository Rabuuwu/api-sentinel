import { describe,it,expect,vi } from 'vitest';
import { render,screen } from '@testing-library/react';
import { delta } from '@/lib/utils';
import { api,setSessionToken } from '@/lib/api';
import { Empty,Metric,StatusBadge } from '@/components/common';
import { defaults,validateMonitor } from '@/components/monitor-editor';

describe('honest metrics',()=>{
 it('does not invent a comparison without previous samples',()=>{
  expect(delta(120,null)).toBeNull();expect(delta(120,0)).toBeNull();expect(delta(null,100)).toBeNull();expect(delta(80,100)).toBe(-20);
 });
 it('renders unknown as awaiting data, not operational',()=>{
  render(<StatusBadge status="UNKNOWN"/>);expect(screen.getByText('Awaiting data')).toBeVisible();expect(screen.queryByText('Operational')).not.toBeInTheDocument();
 });
 it('offers a concrete action for empty data',()=>{
  render(<Empty title="No monitors yet" action={<button>Add monitor</button>}>Start collecting measurements.</Empty>);expect(screen.getByRole('button',{name:'Add monitor'})).toBeVisible();
 });
 it('shows no fabricated period delta',()=>{
  render(<Metric label="P95" value="No data" change={null}/>);expect(screen.getByText('No data')).toBeVisible();expect(screen.queryByText(/previous period/)).not.toBeInTheDocument();
 });
});
describe('monitor form validation',()=>{
 it('accepts DnD Companion readiness URL',()=>expect(validateMonitor({...defaults,name:'DnD Companion',url:'https://dndcompanion-api.onrender.com/ready'})).toBeNull());
 it('rejects embedded secrets',()=>expect(validateMonitor({...defaults,name:'Test',url:'https://user:secret@example.com'})).not.toBeNull());
 it('rejects invalid status ranges',()=>expect(validateMonitor({...defaults,name:'Test',url:'https://example.com',expected_status_min:500,expected_status_max:200})).not.toBeNull());
});
describe('API client',()=>{
 it('does not attach an administrator key to public requests',async()=>{
  const fetchMock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({name:'Public'}),{status:200}));
  setSessionToken('private-key');await api('/public/status-pages/test',{},true);
  expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has('Authorization')).toBe(false);fetchMock.mockRestore();setSessionToken('');
 });
 it('surfaces server errors, never converts them to empty data',async()=>{
  const fetchMock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({error:{message:'Database unavailable'}}),{status:503}));
  await expect(api('/monitors')).rejects.toThrow('Database unavailable');fetchMock.mockRestore();
 });
});
