/** General-site metadata variants and absent booking defaults; no receipt bypass. */
import {mkdirSync,writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {checkedManifest} from '../../hosting/routing.mjs';
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const save=(path,value)=>{mkdirSync(dirname(path),{recursive:true});writeFileSync(path,value);};

export function generateModes({dist,shell,pages,project,manifest,brand,offDescriptions={}}){
 checkedManifest(manifest,project);
 function render(path,mode,booking){
  const entry=pages[path] || (booking?['Appointment','View your appointment details.']:null);
  if(!entry || entry.length!==2)throw Error('Every public page requires reviewed metadata.');
  const title=entry[0]+' | '+brand,description=mode==='off'?(offDescriptions[path] || entry[1]):entry[1];
  let html=shell.replace(/<title>[\s\S]*?<\/title>/,`<title>${escape(title)}</title>`);
  html=html.replace(/(<meta (?:name|property)="(?:title|og:title|twitter:title)" content=")[^"]*/g,`$1${escape(title)}`)
   .replace(/(<meta (?:name|property)="(?:description|og:description|twitter:description)" content=")[^"]*/g,`$1${escape(description)}`)
   .replace(/(<link rel="canonical" href=")[^"]*/g,`$1${escape(project.origin+path)}`)
   .replace(/(<meta (?:name|property)="(?:og:url|twitter:url)" content=")[^"]*/g,`$1${escape(project.origin+path)}`)
   .replace(/(<meta name="robots" content=")[^"]*/g,`$1${booking?'noindex, nofollow':'index, follow'}`)
   .replace('</head>',`<meta name="booking-display-mode" content="${mode}"></head>`);
  if(booking && !html.includes('name="robots"'))html=html.replace('</head>','<meta name="robots" content="noindex, nofollow"></head>');
  return html;
 }
 for(const mode of ['on','off']){
  for(const path of [...manifest.public_paths,...(mode==='on'?manifest.booking_paths:[])]){
   const file=path==='/'?'index.html':path.slice(1)+'.html';
   const html=render(path,mode,manifest.booking_paths.includes(path));
   save(join(dist,'__booking_display',mode,file),html);
   if(mode==='off')save(join(dist,file),html);
  }
  // Private receipts and operator pages are never search-engine listings.
  const listed=manifest.public_paths.concat(mode==='on'?manifest.booking_paths.filter(path=>path==='/booking'||path==='/booking-policy'):[]);
  const xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+listed.map(path=>`\n<url><loc>${escape(project.origin+path)}</loc></url>`).join('')+'\n</urlset>\n';
  save(join(dist,'__booking_display',mode,'sitemap.xml'),xml);if(mode==='off')save(join(dist,'sitemap.xml'),xml);
 }
 const unavailable='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow"><title>Page not found</title></head><body><main><h1>Page not found</h1><p>Contact the practice if you need help.</p><a href="/contact">Send an enquiry</a></main></body></html>';
 for(const path of manifest.booking_paths)save(join(dist,path.slice(1)+'.html'),unavailable);
}
