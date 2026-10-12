/** Only the new Testimonials page and its immediate shared-frame integration. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,include:[
  'tests/public-site/testimonials-*.test.{mjs,jsx}',
  'tests/public-site/refinement-app.test.jsx',
],coverage:{provider:'istanbul',reporter:['text','json-summary','html'],reportsDirectory:'coverage/testimonials',include:[
  'src/pages/Testimonials.jsx','src/site/TestimonialReader.jsx',
  'src/site/testimonials-{content,model,motion}.mjs',
],exclude:[],thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
