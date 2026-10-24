import {defineConfig} from 'vitest/config';
export default defineConfig({test:{environment:'node',pool:'forks',maxWorkers:1,testTimeout:60000,
 include:['tests/public-site/prod-cutover-preflight.test.mjs'],
 coverage:{provider:'istanbul',include:['scripts/check-public-site.mjs'],reporter:['text','json-summary','json'],reportsDirectory:'../docs/qa/2026-10-24-prod-branch-cutover/release/preflight-coverage',thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
