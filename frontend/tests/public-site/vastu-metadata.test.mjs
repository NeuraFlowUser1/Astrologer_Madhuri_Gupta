/** Existing metadata contract, scoped here to qualify its home-only Vastu description change. */
import {test} from 'vitest';
import assert from 'node:assert/strict';
import {pageRegistry,publicPaths,metadataFor,renderMetadata,writePageMetadata,graphFor,safeJson,origin} from '../../src/site/page-metadata.mjs';

test('the 12 reviewed public routes and four utilities have one exact identity',()=>{
 assert.equal(publicPaths.length,12);assert.equal(Object.keys(pageRegistry).length,16);
 for(const [path,data] of Object.entries(pageRegistry)){
  const meta=metadataFor(path);assert.equal(meta.canonical,data.utility?null:origin+path);assert.equal(meta.title,data.title);
  assert.equal(meta.robots,data.utility?'noindex, nofollow':'index, follow');
  assert.equal((data.title.match(/Sarsa Jyotish Sansthan/g)||[]).length,1);
  assert.equal(graphFor(path)===null,data.utility);
 }
 assert.equal(metadataFor('/missing').canonical,null);assert.equal(metadataFor('/missing').robots,'noindex, nofollow');
 for(const path of ['/booking/receipt','/booking-help'])assert.equal(metadataFor(path).referrer,'no-referrer');
});

test('generated and navigated metadata agree without stale or duplicate tags',()=>{
 const html='<!doctype html><html><head><title>Old</title><meta name="description" content="old"><meta name="description" content="duplicate"><script type="application/ld+json">{}</script></head><body><main>Kept content</main></body></html>';
 for(const path of Object.keys(pageRegistry)){
  const doc=document.implementation.createHTMLDocument();doc.documentElement.innerHTML=renderMetadata(html,path);
  for(const target of [path,'/about','/booking/receipt','/services/numerology','/missing']){
   doc.head.insertAdjacentHTML('beforeend','<meta name="description" content="stale duplicate"><link rel="canonical" href="https://incorrect.invalid/a"><link rel="canonical" href="https://incorrect.invalid/b">');
   writePageMetadata(doc,target);const expected=metadataFor(target);
   assert.equal(doc.title,expected.title);assert.equal(doc.querySelectorAll('meta[name="description"]').length,1);
   assert.equal(doc.querySelector('meta[name="description"]').content,expected.description);
   assert.equal(doc.querySelector('meta[name="robots"]').content,expected.robots);
   assert.equal(doc.querySelector('meta[name="twitter:image:alt"]').content,expected.imageAlt);
   assert.equal(doc.querySelector('link[rel="canonical"]')?.href||null,expected.canonical);
   assert.equal(doc.querySelectorAll('script[type="application/ld+json"]').length,graphFor(target)?1:0);
   if(graphFor(target))assert.deepEqual(JSON.parse(doc.querySelector('script[type="application/ld+json"]').textContent),graphFor(target));
   assert.equal(doc.querySelector('main').textContent,'Kept content');
  }
 }
});

test('structured facts are public and script-safe without new endorsements',()=>{
 assert.equal(safeJson('</script>&\u2028\u2029'), '"\\u003c/script\\u003e\\u0026\\u2028\\u2029"');
 const text=JSON.stringify(graphFor('/about'));assert.match(text,/15\+/);assert.match(text,/Shri Vedang/);assert.match(text,/Yogrishi/);
 assert.doesNotMatch(text,/AggregateRating|ReviewAction|verification|activation_epoch|hasCredential/);
 assert.equal(graphFor('/services/kundli-matching')['@graph'].find(item=>item['@type']==='BreadcrumbList').itemListElement.length,3);
});
