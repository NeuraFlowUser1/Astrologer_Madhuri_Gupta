/** Deterministic public metadata; no API calls, customer data or private routes. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pages,origin,titleFor} from '../src/site/page-metadata.mjs';
const dist=resolve(import.meta.dirname,'../dist');
const shell=readFileSync(resolve(dist,'index.html'),'utf8');
const escape=s=>s.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
for(const [path,[,description]] of Object.entries(pages)){
 let html=shell.replace(/<title>.*?<\/title>/,`<title>${escape(titleFor(path))}</title>`);
 html=html.replace(/(<meta (?:name|property)="(?:title|og:title|twitter:title)" content=")[^"]*/g,`$1${escape(titleFor(path))}`);
 html=html.replace(/(<meta (?:name|property)="(?:description|og:description|twitter:description)" content=")[^"]*/g,`$1${escape(description)}`);
 html=html.replace(/(<link rel="canonical" href=")[^"]*/g,`$1${origin+path}`);
 html=html.replace(/(<meta (?:name|property)="(?:og:url|twitter:url)" content=")[^"]*/g,`$1${origin+path}`);
 const file=resolve(dist,path==='/'?'index.html':path.slice(1)+'.html');mkdirSync(dirname(file),{recursive:true});writeFileSync(file,html);
}
writeFileSync(resolve(dist,'sitemap.xml'),'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+Object.keys(pages).map(path=>`\n<url><loc>${origin+path}</loc></url>`).join('')+'\n</urlset>\n');
console.log('Generated public-route metadata and clean sitemap. No private routes rendered.');
