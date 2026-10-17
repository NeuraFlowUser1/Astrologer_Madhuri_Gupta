/** Focused on the approved Home/About/header changes; no coverage exclusions. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,
 include:['tests/public-site/hero-brand.test.jsx','tests/public-site/hero-build.test.mjs','tests/public-site/restored-pages.test.jsx','tests/public-site/refinement-app.test.jsx','tests/public-site/refinement-helpers.test.jsx'],
 coverage:{provider:'istanbul',reporter:['text','json-summary'],reportsDirectory:'coverage/hero-brand',
 include:['src/site/HeroDetails.jsx','src/site/hero-content.mjs','src/site/hero-band-motion.mjs','src/site/about-layout.mjs','src/site/SiteFrame.jsx','src/site/page-metadata.mjs','src/pages/Home.jsx','src/pages/About.jsx','scripts/hero-static.mjs','scripts/public-pages.mjs'],exclude:[],
 thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90}}}});
