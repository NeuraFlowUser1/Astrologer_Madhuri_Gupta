/** Focused checks for the approved public refinement; no shared-system or hosted suite. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,include:[
 'tests/public-site/refinement-*.test.{mjs,jsx}',
 'tests/public-site/restored-pages.test.jsx','tests/public-site/booking-frame.test.jsx',
 'tests/public-site/restore-contact.test.jsx','tests/public-site/restore-layout.test.mjs',
 'tests/public-site/lifecycle.test.mjs','tests/public-site/entrypoints.test.mjs'
],coverage:{provider:'istanbul',reporter:['text','json','json-summary','html'],reportsDirectory:'coverage/refinement',include:[
 'src/App.jsx','src/pages/{Home,About,Services,ServiceDetail,KundliPrediction,ContactPage,Booking,PolicyPage}.jsx',
 'src/site/{SiteFrame,BackToTop,MarginArt,ServiceArtwork}.jsx',
 'src/site/{public-scroll,home-enhancements,about-layout,about-motion,page-metadata}.mjs',
 'scripts/check-public-site.mjs'
],exclude:[],thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
