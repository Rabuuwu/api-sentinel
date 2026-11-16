import { test,expect } from '@playwright/test';
// Run only against an isolated Sentinel stack using sentinel_test. Never production.
const enabled=process.env.SENTINEL_E2E_ISOLATED==='1'&&!!process.env.SENTINEL_E2E_KEY&&!!process.env.SENTINEL_E2E_URL;
test.skip(!enabled,'Set SENTINEL_E2E_ISOLATED=1, SENTINEL_E2E_URL and SENTINEL_E2E_KEY for an isolated test stack.');
test('real API: login, create monitor, pause, metrics, remove and lock',async({page,request})=>{
 const name=`E2E ${Date.now()}`;const headers={'X-API-Key':process.env.SENTINEL_E2E_KEY!};let monitorId:string|undefined;
 try{
 await page.goto('/');await page.getByLabel('Workspace API key').fill(process.env.SENTINEL_E2E_KEY!);await page.getByRole('button',{name:'Open workspace'}).click();await expect(page.getByRole('heading',{name:'Workspace overview'})).toBeVisible();
 await page.getByRole('button',{name:'Create monitor'}).click();await page.getByLabel('Name',{exact:true}).fill(name);await page.getByLabel('URL',{exact:true}).fill('https://example.com');await page.getByRole('button',{name:'Save monitor'}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
 const response=await request.get('/api/v1/overview',{headers,params:{q:name}});expect(response.ok()).toBeTruthy();monitorId=(await response.json()).items[0].id;
 await page.goto(`/monitors/${monitorId}`); // full reload intentionally locks the in-memory session
 await page.getByLabel('Workspace API key').fill(process.env.SENTINEL_E2E_KEY!);await page.getByRole('button',{name:'Open workspace'}).click();await expect(page.getByRole('heading',{name})).toBeVisible();
 await page.getByRole('button',{name:'Pause',exact:true}).click();await expect(page.getByRole('button',{name:'Resume',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Uptime history'})).toBeVisible();await expect(page.getByRole('heading',{name:'Timeline'})).toBeVisible();
 await page.getByRole('button',{name:'Delete monitor',exact:true}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();await expect(page.getByRole('heading',{name:'Workspace overview'})).toBeVisible();
 await page.getByRole('button',{name:'Lock workspace'}).click();await expect(page.getByLabel('Workspace API key')).toBeVisible();expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
 }finally{if(monitorId)await request.delete(`/api/v1/monitors/${monitorId}`,{headers});}
});
