// Run after chrome_fixture.py reports ready. No hosted provider is contacted.
import {fileURLToPath} from 'node:url';
import {chromium} from '../../frontend/node_modules/playwright-core/index.mjs';
import journey from './chrome_journey.mjs';

const root=fileURLToPath(new URL('./artifacts/',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();
  const result=await journey(page,root);
  console.log(JSON.stringify(result));
} finally {await browser.close();}
