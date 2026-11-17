import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {EmailFlow} from '@/components/email-flow';
import {api} from '@/lib/api';
vi.mock('@/lib/api',()=>({api:vi.fn(),json:(method:string,body:unknown)=>({method,body:JSON.stringify(body)})}));
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState(null,'','/');});
it('does not consume a verification link on page load and removes the token from history',async()=>{
 window.history.replaceState(null,'','/#/account-link?purpose=verify&token=private-token');
 vi.mocked(api).mockResolvedValue({message:'Email confirmed. Sign in again.'});
 render(<EmailFlow mode="link"/>);
 expect(api).not.toHaveBeenCalled();expect(window.location.hash).toBe('#/account-link');
 await userEvent.click(screen.getByRole('button',{name:'Confirm email'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/auth/email/verify',expect.objectContaining({body:JSON.stringify({token:'private-token'})}),true));
 expect(await screen.findByRole('status')).toHaveTextContent('Email confirmed');
});
it('requires matching reset passwords before making a request',async()=>{
 window.history.replaceState(null,'','/#/account-link?purpose=reset&token=private-token');
 render(<EmailFlow mode="link"/>);const user=userEvent.setup();
 await user.type(screen.getByLabelText('New password',{exact:true}),'long enough password 123');
 await user.type(screen.getByLabelText('Confirm new password'),'does not match');
 await user.click(screen.getByRole('button',{name:'Set new password'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Passwords do not match');expect(api).not.toHaveBeenCalled();
});
it('requests recovery by email without implying whether an account exists',async()=>{
 vi.mocked(api).mockResolvedValue({message:'If the details match an eligible account, an email will arrive shortly.'});
 render(<EmailFlow mode="forgot"/>);const user=userEvent.setup();
 await user.type(screen.getByLabelText('Email address'),'alice@example.com');await user.click(screen.getByRole('button',{name:'Send email'}));
 expect(await screen.findByRole('status')).toHaveTextContent('If the details match');
 expect(vi.mocked(api).mock.calls[0][0]).toBe('/auth/password-reset/request');
});
