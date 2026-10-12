import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,include:['tests/public-site/certifications-*.test.{mjs,jsx}'],coverage:{provider:'istanbul',reporter:['text','json-summary'],reportsDirectory:'coverage/certifications',include:['src/site/Certifications.jsx','src/site/certificates-content.mjs','src/site/certifications-motion.mjs','src/site/about-layout.mjs'],exclude:[],thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
