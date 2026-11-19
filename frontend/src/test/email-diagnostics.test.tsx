import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {render,screen} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {EmailSettings} from '@/components/email-settings';
import {api} from '@/lib/api';
vi.mock('@/lib/api',()=>({api:vi.fn(),json:vi.fn()}));
beforeEach(()=>vi.clearAllMocks());
function show(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><EmailSettings/></QueryClientProvider>);}
it('shows safe delivery diagnostics and instructs the admin to request a fresh link',async()=>{
 vi.mocked(api).mockImplementation(async(path)=>path==='/auth/me'?{is_admin:true,mail_enabled:true,email:null,pending_email:null}:{enabled:true,deliveries:{FAILED:1},last_failure:{code:'GMAIL_AUTH_INVALID_GRANT',at:'2026-11-19T12:00:00Z'}} as never);
 show();expect(await screen.findByText(/GMAIL_AUTH_INVALID_GRANT/)).toHaveTextContent('request a new link');
 expect(screen.getByText(/Counts cover active links only/)).toBeInTheDocument();
});
it('does not request admin diagnostics for a regular account',async()=>{
 vi.mocked(api).mockResolvedValue({is_admin:false,mail_enabled:true,email:'alice@example.com',pending_email:null});
 show();await screen.findByText(/Verified address/);
 expect(vi.mocked(api).mock.calls.map(c=>c[0])).toEqual(['/auth/me']);
});
