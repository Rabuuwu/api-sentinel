import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(()=>{vi.restoreAllMocks();vi.unstubAllEnvs();vi.resetModules();});
describe('remote dashboard transport',()=>{
 it('uses the configured HTTPS API without cookies or following redirects',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','https://sentinel.example.com/api/v1/');
  vi.resetModules();
  const {api,setSessionToken}=await import('@/lib/api');
  const fetchMock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response('{}'));
  setSessionToken('test-key');await api('/system');
  expect(fetchMock.mock.calls[0][0]).toBe('https://sentinel.example.com/api/v1/system');
  const options=fetchMock.mock.calls[0][1];
  expect(options?.credentials).toBe('omit');
  expect(options?.redirect).toBe('error');
  expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-key');
  setSessionToken('');
 });
 it('explains unreachable external API instead of returning fake data',async()=>{
  vi.spyOn(globalThis,'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
  const {api}=await import('@/lib/api');
  await expect(api('/system')).rejects.toThrow(/HTTPS address and CORS/);
 });
});
