/** Read-only Sarsa release preflight. No provider settings or customer writes. */
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,statSync} from 'node:fs';
import {resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {pages,origin,titleFor} from '../src/site/page-metadata.mjs';
import copy from '../src/site/public-copy.json' with {type:'json'};
import map from '../src/site/map-location.json' with {type:'json'};

export function listFiles(root){return readdirSync(root,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?listFiles(resolve(root,entry.name)):[resolve(root,entry.name)]);}
export function checkAssets(assets,publicRoot){
 for(const path of listFiles(publicRoot)){const key='/'+relative(publicRoot,path).replaceAll('\\','/');assert.ok(['general','generated','booking'].includes(assets[key]),'Unclassified public asset: '+key);}
 const fonts=listFiles(resolve(publicRoot,'fonts')).filter(p=>p.endsWith('.woff2'));assert.ok(fonts.reduce((sum,p)=>sum+statSync(p).size,0)<=300*1024,'New font budget exceeded');
 for(const p of listFiles(resolve(publicRoot,'media/sarsa-public')).filter(p=>p.endsWith('.svg')))assert.ok(statSync(p).size<=20*1024,'Vector budget exceeded');
 assert.ok(statSync(resolve(publicRoot,'media/sarsa-public/consultation-still-life-desktop.webp')).size<=300*1024);
 assert.ok(statSync(resolve(publicRoot,'media/sarsa-public/consultation-still-life-phone.webp')).size<=160*1024);
}
export function checkProtectedPaths(paths){
 const protectedPaths=paths.filter(path=>path.startsWith('appointment-system/')||path.startsWith('workers/')||path.startsWith('api/')||(path.startsWith('appointment-settings/')&&path!=='appointment-settings/public-assets.json')||['requirements.txt','pyproject.toml','vercel.json'].includes(path));
 assert.deepEqual(protectedPaths,[],'Protected backend or settings changed');
}
export function runChecks({root=resolve(import.meta.dirname,'../..'),baseline='fef4f4e48eb87fe748c9d05b3be3ce4f27f6a548'}={}){
 const frontend=resolve(root,'frontend'),assets=JSON.parse(readFileSync(resolve(root,'appointment-settings/public-assets.json')));
 checkAssets(assets,resolve(frontend,'public'));
 assert.equal(origin,'https://www.sarsajyotishsansthan.com');assert.equal(pages['/services'][0],'Services');assert.equal(Object.keys(pages).length,12);
 assert.deepEqual(copy.services.map(s=>s.id),['kundli-matching','kundli-prediction','vastu-consultation','numerology']);assert.equal(copy.home.faq.length,8);assert.equal(copy.contact.faq.length,4);
 assert.equal(map.owner_link,'https://maps.app.goo.gl/CwQftW8iYfxAZFDo8');assert.ok(map.embed_url.startsWith('https://www.google.com/maps/embed?pb='));assert.equal(copy.brand.address,'8, Gailana Road, LIC Colony, Agra - 282007');
 for(const path of Object.keys(pages))assert.ok(titleFor(path).endsWith(' | Sarsa Jyotish Sansthan'));
 // Compare the complete committed and working candidate with the approved start,
 // including new untracked files. HEAD-only comparison misses committed changes.
 const changed=execFileSync('git',['diff','--name-only',baseline],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const untracked=execFileSync('git',['ls-files','--others','--exclude-standard'],{cwd:root,encoding:'utf8'}).trim().split('\n');
 checkProtectedPaths([...changed,...untracked]);
 const source=listFiles(resolve(frontend,'src')).filter(p=>/\.(?:jsx?|mjs|tsx?)$/.test(p));
 assert.ok(source.length>20,'Unexpected working-source denominator');
 console.log(JSON.stringify({checks:'passed',public_routes:12,working_source_files:source.length,protected_diff:'unchanged',new_fonts_bytes:listFiles(resolve(frontend,'public/fonts')).filter(p=>p.endsWith('.woff2')).reduce((sum,p)=>sum+statSync(p).size,0)}));
 return {source:source.map(p=>relative(frontend,p)),routes:Object.keys(pages)};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))runChecks();
