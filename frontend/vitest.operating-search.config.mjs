/** Focused receiving-app regression checks for the 22 October programme. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],test:{environment:'jsdom',pool:'vmThreads',maxWorkers:2,testTimeout:15000,include:[
 'tests/public-site/hero-brand.test.jsx','tests/public-site/hero-build.test.mjs',
 'tests/public-site/refinement-app.test.jsx','tests/public-site/refinement-helpers.test.jsx',
 'tests/public-site/restore-contact.test.jsx','tests/public-site/restored-pages.test.jsx',
 'tests/public-site/bootstrap.test.jsx','tests/public-site/lifecycle.test.mjs',
]}});
