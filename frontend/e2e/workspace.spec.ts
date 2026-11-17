import {test,expect} from '@playwright/test';
// Only a dedicated test stack. CI provisions sentinel_test, never a production branch.
const enabled=process.env.SENTINEL_E2E_ISOLATED==='1'&&!!process.env.SENTINEL_E2E_KEY&&!!process.env.SENTINEL_E2E_URL;
test.skip(!enabled,'Set SENTINEL_E2E_ISOLATED=1, SENTINEL_E2E_URL and SENTINEL_E2E_KEY for an isolated test stack.');
test('accounts: login, monitor CRUD, owner isolation and server logout',async({page,request,browser})=>{
 const username='e2e-owner',password='e2e test-only passphrase 1234',name=`E2E ${Date.now()}`;
 const setup=await request.get('/api/v1/auth/setup');expect(setup.ok()).toBeTruthy();
 if((await setup.json()).setup_required){const boot=await request.post('/api/v1/auth/bootstrap',{data:{username,password,setup_key:process.env.SENTINEL_E2E_KEY}});expect(boot.ok()).toBeTruthy();}
 const login=await request.post('/api/v1/auth/login',{data:{username,password}});expect(login.ok()).toBeTruthy();
 const token=(await login.json()).token,headers={Authorization:`Bearer ${token}`};let monitorId:string|undefined;
 const signIn=async()=>{await page.getByLabel('Username',{exact:true}).fill(username);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();};
 try{
  await page.goto('/');await signIn();await expect(page.getByRole('heading',{name:'Workspace overview'})).toBeVisible();
  await page.getByRole('button',{name:'Create monitor'}).click();await page.getByLabel('Name',{exact:true}).fill(name);await page.getByLabel('URL',{exact:true}).fill('https://example.com');await page.getByRole('button',{name:'Save monitor'}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
  const response=await request.get('/api/v1/overview',{headers,params:{q:name}});expect(response.ok()).toBeTruthy();monitorId=(await response.json()).items[0].id;
  const invitation=await request.post('/api/v1/auth/invitations',{headers});expect(invitation.ok()).toBeTruthy();
  const other=await browser.newContext();const guest=await other.newPage();
  try{
   await guest.goto('/');await guest.getByRole('button',{name:'I have an invitation'}).click();await guest.getByLabel('Username',{exact:true}).fill(`guest-e2e-${Date.now()}`);await guest.getByLabel('Password',{exact:true}).fill(password);await guest.getByLabel('Confirm password').fill(password);await guest.getByLabel('Invitation code').fill((await invitation.json()).invitation);await guest.getByRole('button',{name:'Create account',exact:true}).click();await expect(guest.getByRole('heading',{name:'Workspace overview'})).toBeVisible();await expect(guest.getByText(name,{exact:true})).toHaveCount(0);
  }finally{await other.close();}
  await page.goto(`/monitors/${monitorId}`);await signIn();await expect(page.getByRole('heading',{name})).toBeVisible();
  await page.getByRole('button',{name:'Pause',exact:true}).click();await expect(page.getByRole('button',{name:'Resume',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Uptime history'})).toBeVisible();
  await page.getByRole('button',{name:'Delete monitor',exact:true}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();await expect(page.getByRole('heading',{name:'Workspace overview'})).toBeVisible();
  await page.getByRole('button',{name:'Lock workspace'}).click();await expect(page.getByLabel('Username',{exact:true})).toBeVisible();expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
  expect((await request.post('/api/v1/auth/logout',{headers})).status()).toBe(204);
  expect((await request.get('/api/v1/auth/me',{headers})).status()).toBe(401);
 }finally{if(monitorId)await request.delete(`/api/v1/monitors/${monitorId}`,{headers});}
});
