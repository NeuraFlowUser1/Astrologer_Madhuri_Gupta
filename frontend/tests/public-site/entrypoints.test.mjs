// @vitest-environment node
import {test,expect} from 'vitest';
import {readFileSync,existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {runChecks,checkAssets,checkProtectedPaths} from '../../scripts/check-public-site.mjs';
import {pages,origin,titleFor} from '../../src/site/page-metadata.mjs';
test('protected-path checks reject every backend boundary and retain the public asset exception',()=>{
 for(const path of ['appointment-system/engine/x.py','workers/service.js','api/index.py','appointment-settings/project.json','requirements.txt','pyproject.toml','vercel.json'])expect(()=>checkProtectedPaths([path])).toThrow('Protected backend');
 expect(()=>checkProtectedPaths(['frontend/src/App.jsx','appointment-settings/public-assets.json'])).not.toThrow();
});
test('release preflight inventories all active source and rejects an unclassified public file',()=>{
 const result=runChecks();expect(result.source).toContain('src/booking/booking-ui.jsx');expect(result.routes).toHaveLength(12);
 const publicRoot=new URL('../../public',import.meta.url).pathname,assets=JSON.parse(readFileSync(new URL('../../../appointment-settings/public-assets.json',import.meta.url)));
 delete assets['/media/consultation-still-life.png'];expect(()=>checkAssets(assets,publicRoot)).toThrow('Unclassified public asset');
});
test('the real public-page build entrypoint creates both modes and exact asset classes',async()=>{
 await import('../../scripts/public-pages.mjs');
 await import('../../scripts/public-pages.mjs?repeat');
 const manifest=JSON.parse(readFileSync(new URL('../../dist/appointment-surface-manifest.json',import.meta.url)));
 expect(manifest.public_paths).toContain('/services');expect(manifest.booking_paths).toContain('/booking-help');expect(manifest.assets['/media/consultation-still-life.png']).toBe('general');
 expect(readFileSync(new URL('../../dist/__booking_display/on/index.html',import.meta.url),'utf8')).not.toContain('sarsa-public/');
 for(const mode of ['on','off'])for(const path of Object.keys(pages)){
  const file=new URL('../../dist/__booking_display/'+mode+'/'+(path==='/'?'index':path.slice(1))+'.html',import.meta.url);
  if(mode==='off'&&['/booking','/booking-policy'].includes(path)){expect(existsSync(file)).toBe(false);continue;}
  const html=readFileSync(file,'utf8');expect(html).toContain('<title>'+titleFor(path)+'</title>');expect(html).toContain('rel="canonical" href="'+origin+path+'"');expect(html).toContain('name="robots" content="'+(manifest.booking_paths.includes(path)?'noindex, nofollow':'index, follow')+'"');expect(html.match(/name="booking-display-mode"/g)).toHaveLength(1);expect(html).toContain('name="booking-display-mode" content="'+mode+'"');
 }
 for(const path of ['booking/receipt','booking-help'])expect(readFileSync(new URL('../../dist/__booking_display/on/'+path+'.html',import.meta.url),'utf8')).toContain('name="robots" content="noindex, nofollow"');
 const {default:routing}=await import('../../proxy.js');expect(typeof routing).toBe('function');
});
test('native build/proxy helpers execute with collected source-bound instrumentation',()=>{
 // Tailwind uses Node's module hooks, unavailable inside Vitest's VM realm.
 const result=JSON.parse(execFileSync(process.execPath,[new URL('./native-helpers.mjs',import.meta.url).pathname],{encoding:'utf8'}));expect(result.checks).toBe(10);expect(result.files).toBe(4);
},60000);
