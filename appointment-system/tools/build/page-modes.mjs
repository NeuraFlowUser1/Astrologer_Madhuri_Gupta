/** General-site metadata variants and absent booking defaults; no receipt bypass. */
import {mkdirSync,writeFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {checkedManifest} from '../../hosting/routing.mjs';
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const save=(path,value)=>{mkdirSync(dirname(path),{recursive:true});writeFileSync(path,value);};

export function generateModes({dist,shell,pages,project,manifest,brand,offDescriptions={},renderPage}){
 checkedManifest(manifest,project);
 if(renderPage!==undefined && typeof renderPage!=='function')throw TypeError('A page renderer must be a function.');
 function metadata(html,{title,description,canonical,robots,mode}){
  if(typeof html!=='string' || !html.includes('</head>') || !html.includes('</body>'))throw Error('A complete page document is required.');
  const tag=(pattern,value)=>{
   let found=false;
   html=html.replace(pattern,()=>{if(found)return '';found=true;return value;});
   if(!found)html=html.replace('</head>',value+'</head>');
  };
  tag(/<title>[\s\S]*?<\/title>/gi,`<title>${escape(title)}</title>`);
  for(const [name,value] of Object.entries({description,robots,'booking-display-mode':mode})){
   const pattern=new RegExp(`<meta\\s+name=(?:"${name}"|'${name}')\\s+content=(?:"[^"]*"|'[^']*')\\s*\\/?>\\s*`,'gi');
   tag(pattern,`<meta name="${name}" content="${escape(value)}">`);
  }
  html=html.replace(/(<meta name="googlebot" content=")[^"]*/g,`$1${robots}`);
  tag(/<link\s+rel=["']canonical["']\s+href=["'][^"']*["']\s*\/?>/gi,`<link rel="canonical" href="${escape(canonical)}">`);
  html=html.replace(/(<meta (?:name|property)="(?:title|og:title|twitter:title)" content=")[^"]*/g,`$1${escape(title)}`)
   .replace(/(<meta (?:name|property)="(?:og:description|twitter:description)" content=")[^"]*/g,`$1${escape(description)}`)
   .replace(/(<meta (?:name|property)="(?:og:url|twitter:url)" content=")[^"]*/g,`$1${escape(canonical)}`);
  return html;
 }
 function render(path,mode,booking){
  const entry=pages[path] || (booking?['Appointment','View your appointment details.']:null);
  const legacy=Array.isArray(entry);
  if(!entry || (legacy?entry.length!==2:typeof entry!=='object') || typeof(legacy?entry[0]:entry.title)!=='string'
   || typeof(legacy?entry[1]:entry.description)!=='string')throw Error('Every public page requires reviewed metadata.');
  const title=legacy?entry[0]+' | '+brand:entry.title;
  const description=mode==='off'?(offDescriptions[path] || (legacy?entry[1]:entry.description)):(legacy?entry[1]:entry.description);
  const intent={title,description,canonical:project.origin+path,robots:booking?'noindex, nofollow':'index, follow',mode};
  let html=metadata(shell,intent);
  if(renderPage)html=metadata(renderPage({path,booking,html,...intent}),intent);
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
  const listed=manifest.public_paths;
  const xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+listed.map(path=>`\n<url><loc>${escape(project.origin+path)}</loc></url>`).join('')+'\n</urlset>\n';
  save(join(dist,'__booking_display',mode,'sitemap.xml'),xml);if(mode==='off')save(join(dist,'sitemap.xml'),xml);
 }
 const unavailable='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow"><title>Page not found</title></head><body><main><h1>Page not found</h1><p>Contact the practice if you need help.</p><a href="/contact">Send an enquiry</a></main></body></html>';
 for(const path of manifest.booking_paths)save(join(dist,path.slice(1)+'.html'),unavailable);
}
