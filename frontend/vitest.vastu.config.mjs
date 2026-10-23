/** Changed-source qualification only; no shared package, provider or full-site suite. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,include:[
 'tests/public-site/vastu-*.test.{mjs,jsx}',
 'tests/public-site/refinement-pages.test.jsx','tests/public-site/restored-pages.test.jsx',
 'tests/public-site/hero-brand.test.jsx','tests/public-site/refinement-app.test.jsx',
],coverage:{provider:'istanbul',reporter:['text','json','json-summary'],reportsDirectory:'coverage/vastu',include:[
 'src/pages/{Home,Services,ServiceDetail}.jsx',
 'src/site/{VastuDetails,ServiceVisualStory}.jsx',
 'src/site/{vastu-content,vastu-motion,service-motion,service-visual-content,page-metadata}.mjs',
],exclude:[],thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
