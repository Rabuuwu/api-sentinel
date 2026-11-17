import {beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {SignIn} from '@/components/sign-in';
import {api,setSessionToken} from '@/lib/api';
vi.mock('@/lib/api',()=>({api:vi.fn(),setSessionToken:vi.fn(),apiBase:'/api/v1',json:(method:string,body:unknown)=>({method,body:JSON.stringify(body)})}));
const mocked=vi.mocked(api);
function mount(){const done=vi.fn();render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><SignIn onSignedIn={done}/></QueryClientProvider>);return done;}
beforeEach(()=>{vi.clearAllMocks();});
describe('account entry',()=>{
 it('signs in with credentials and stores only the opaque session in memory',async()=>{
  mocked.mockResolvedValueOnce({setup_required:false}).mockResolvedValueOnce({token:'opaque-session'});
  const done=mount(),user=userEvent.setup();
  await user.type(await screen.findByLabelText('Username'),'alice');
  await user.type(screen.getByLabelText('Password',{exact:true}),'a sufficiently long password');
  await user.click(screen.getByRole('button',{name:'Sign in'}));
  await waitFor(()=>expect(done).toHaveBeenCalled());
  expect(setSessionToken).toHaveBeenCalledWith('opaque-session');
  expect(mocked.mock.calls[1][0]).toBe('/auth/login');
  expect(mocked.mock.calls[1][2]).toBe(true);
  expect(localStorage.length+sessionStorage.length).toBe(0);
 });
 it('reports a failed login without opening the workspace',async()=>{
  mocked.mockResolvedValueOnce({setup_required:false}).mockRejectedValueOnce(new Error('Invalid username or password'));
  const done=mount(),user=userEvent.setup();
  await user.type(await screen.findByLabelText('Username'),'alice');
  await user.type(screen.getByLabelText('Password',{exact:true}),'a sufficiently long password');
  await user.click(screen.getByRole('button',{name:'Sign in'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password');
  expect(done).not.toHaveBeenCalled();expect(setSessionToken).not.toHaveBeenCalled();
 });
 it('requires confirmation and the setup key before claiming legacy data',async()=>{
  mocked.mockResolvedValueOnce({setup_required:true});
  mount();const user=userEvent.setup();
  await user.type(await screen.findByLabelText('Username'),'owner');
  await user.type(screen.getByLabelText('Password',{exact:true}),'a sufficiently long password');
  await user.type(screen.getByLabelText('Confirm password'),'different password');
  await user.type(screen.getByLabelText('Owner setup key'),'x'.repeat(40));
  await user.click(screen.getByRole('button',{name:'Create account'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Passwords do not match');
  expect(mocked).toHaveBeenCalledTimes(1);
 });
});
