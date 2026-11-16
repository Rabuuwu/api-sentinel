import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./e2e',fullyParallel:false,retries:0,use:{baseURL:process.env.SENTINEL_E2E_URL,trace:'retain-on-failure',screenshot:'only-on-failure'},reporter:'list'});
