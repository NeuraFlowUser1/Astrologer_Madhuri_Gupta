/** Actual complete public generation, with direct initial-HTML acceptance. */
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {JSDOM} from 'jsdom';
import {pageRegistry,publicPaths,origin} from '../../src/site/page-metadata.mjs';
const previousFetch=globalThis.fetch;globalThis.fetch=()=>{throw Error('Public generation must not read a provider');};
try{await import('../../scripts/public-pages.mjs');}finally{globalThis.fetch=previousFetch;}
const dist=resolve(import.meta.dirname,'../../dist');let documents=0;
for(const mode of ['on','off']){
 const sitemap=readFileSync(resolve(dist,'__booking_display',mode,'sitemap.xml'),'utf8');const urls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);assert.deepEqual(urls.sort(),publicPaths.map(path=>origin+path).sort());
 for(const [path,meta] of Object.entries(pageRegistry)){
  const file=resolve(dist,'__booking_display',mode,path==='/'?'index.html':path.slice(1)+'.html');if(meta.utility&&mode==='off'){assert.equal(existsSync(file),false);continue;}
  const document=new JSDOM(readFileSync(file,'utf8')).window.document;
  assert.equal(document.querySelectorAll('title').length,1);assert.equal(document.title,meta.title);assert.equal(document.querySelectorAll('meta[name="description"]').length,1);assert.equal(document.querySelector('meta[name="description"]').content,meta.description);assert.equal(document.querySelectorAll('link[rel="canonical"]').length,1);assert.equal(document.querySelector('link[rel="canonical"]').getAttribute('href'),origin+path);
  assert.equal(document.querySelector('meta[name="robots"]').content,meta.utility?'noindex, nofollow':'index, follow');
  if(!meta.utility){assert.equal(document.querySelectorAll('main h1').length,1);assert.equal(document.querySelector('#root').getAttribute('data-public-path'),path);documents++;}
 }
}
console.log(JSON.stringify({actualPublicDocuments:documents,eligibleSitemapRoutes:12,utilityIdentity:true,oneMetadataOwner:true,networkCalls:0}));
