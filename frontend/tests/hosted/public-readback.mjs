/** Official public GET responses only. Never mounts a controller or sends input. */
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {createHash} from 'node:crypto';
import {JSDOM} from 'jsdom';
import {origin,pageRegistry,publicPaths,metadataFor,graphFor,shareImage} from '../../src/site/page-metadata.mjs';
const digest=value=>createHash('sha256').update(value).digest('hex');
export async function checkPublicReadback(directory){
 const output=resolve(directory);await mkdir(output,{recursive:true});
 const report={started:new Date().toISOString(),scope:'Official unauthenticated GET responses; no submissions or account operations.',pages:[],utilityQueries:[],assets:[],passed:false};
 async function get(path){const response=await fetch(origin+path,{redirect:'manual',signal:AbortSignal.timeout(45000)});assert.equal(response.url,origin+path);return response;}
 try{
  for(const [path,page] of Object.entries(pageRegistry)){
   const response=await get(path);assert.equal(response.status,200,path+' HTTP');assert.match(response.headers.get('content-type')||'',/text\/html/);
   const html=await response.text(),document=new JSDOM(html).window.document,meta=metadataFor(path);
   assert.equal(document.querySelectorAll('title').length,1);assert.equal(document.title,meta.title);
   for(const [name,expected] of [['description',meta.description],['robots',meta.robots],['googlebot',meta.robots],['referrer',meta.referrer]]){const nodes=document.querySelectorAll(`meta[name="${name}"]`);assert.equal(nodes.length,1,path+' '+name+' owner');assert.equal(nodes[0].content,expected);}
   const canonical=document.querySelectorAll('link[rel="canonical"]');assert.equal(canonical.length,page.utility?0:1);if(!page.utility)assert.equal(canonical[0].getAttribute('href'),origin+path);
   assert.equal(document.querySelector('meta[property="og:image"]').content,shareImage);assert.equal(document.querySelector('meta[name="twitter:image"]').content,shareImage);
   if(page.utility){assert.match(response.headers.get('x-robots-tag')||'',/noindex/);assert.equal(document.querySelectorAll('script[type="application/ld+json"]').length,0);}
   else{
    assert.doesNotMatch(response.headers.get('x-robots-tag')||'',/noindex/i);assert.equal(document.querySelectorAll('main h1').length,1);
    const root=document.querySelector('#root');assert.equal(root.dataset.publicPath,path);assert.equal(root.dataset.publicMode,'on');assert.equal(root.dataset.publicRender,'sarsa-public-v1');
    const graph=document.querySelectorAll('script[type="application/ld+json"]');assert.equal(graph.length,1);assert.deepEqual(JSON.parse(graph[0].textContent),graphFor(path));
    if(path==='/contact'){assert.equal(document.querySelector('#enquiry').getAttribute('method'),'post');assert.equal(document.querySelector('#enquiry fieldset').disabled,true);}
   }
   report.pages.push({path,status:response.status,title:document.title,utility:page.utility,canonicalCount:canonical.length,mainH1:document.querySelectorAll('main h1').length,htmlCharacters:html.length,robotsHeader:response.headers.get('x-robots-tag')});
   document.defaultView.close();
  }
  for(const path of Object.keys(pageRegistry).filter(path=>pageRegistry[path].utility)){
   const address=path+'?source=identity-review',response=await get(address);assert.equal(response.status,200);
   const document=new JSDOM(await response.text()).window.document;
   assert.equal(document.title,metadataFor(path).title);assert.equal(document.querySelectorAll('link[rel="canonical"],script[type="application/ld+json"]').length,0);
   assert.equal(document.querySelector('meta[name="robots"]').content,'noindex, nofollow');assert.match(response.headers.get('x-robots-tag')||'',/noindex/);
   report.utilityQueries.push({path:address,status:response.status,canonicalCount:0,graphs:0,noindex:true});document.defaultView.close();
  }
  const sitemapResponse=await get('/sitemap.xml');assert.equal(sitemapResponse.status,200);const sitemap=await sitemapResponse.text();assert.deepEqual([...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]).sort(),publicPaths.map(path=>origin+path).sort());
  const robotsResponse=await get('/robots.txt');assert.equal(robotsResponse.status,200);assert.match(robotsResponse.headers.get('content-type')||'',/text\/plain/);const robots=await robotsResponse.text();assert(robots.includes('Sitemap: '+origin+'/sitemap.xml'));assert.doesNotMatch(robots,/Disallow:\s*\/booking-help\s*$/m);
  const unknown=await get('/not-a-real-page-20261022');assert.equal(unknown.status,404);report.unknownStatus=unknown.status;
  for(const name of ['sarsa-madhuri-share-20261022.webp','consultation-still-life-768.webp','consultation-still-life-1280.webp','consultation-still-life-1920.webp']){
   const response=await get('/media/'+name);assert.equal(response.status,200);assert.match(response.headers.get('content-type')||'',/image\/webp/);const bytes=Buffer.from(await response.arrayBuffer()),source=await readFile(resolve(import.meta.dirname,'../../public/media',name));assert.equal(digest(bytes),digest(source),name+' published bytes');report.assets.push({name,bytes:bytes.length,sha256:digest(bytes)});
  }
  report.sitemapRoutes=publicPaths.length;report.passed=true;return report;
 }catch(error){report.error=String(error);throw error;}
 finally{report.finished=new Date().toISOString();await writeFile(join(output,'public-readback.json'),JSON.stringify(report,null,2)+'\n');}
}
