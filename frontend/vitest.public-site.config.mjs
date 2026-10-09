import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,include:['tests/public-site/**/*.test.{mjs,jsx}','tests/verification/{booking-flow,enquiry-flow,callback-recovery}.test.{mjs,jsx}'],
 coverage:{provider:'istanbul',reporter:['text','json','json-summary'],reportsDirectory:process.env.SARSA_EVIDENCE_DIR||'coverage/public-site',
 include:['src/**/*.{js,mjs,jsx,ts,tsx}','scripts/**/*.mjs','proxy.js','vite.config.js'],exclude:[],thresholds:{statements:90,branches:90,functions:90,lines:90}}}});
