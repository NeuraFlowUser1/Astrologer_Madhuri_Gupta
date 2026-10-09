/** Read-only Sarsa release preflight. No provider settings or customer writes. */
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,statSync} from 'node:fs';
import {resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {pages,origin,titleFor} from '../src/site/page-metadata.mjs';

export function listFiles(root){return readdirSync(root,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?listFiles(resolve(root,entry.name)):[resolve(root,entry.name)]);}
export function checkAssets(assets,publicRoot){
 for(const path of listFiles(publicRoot)){const key='/'+relative(publicRoot,path).replaceAll('\\','/');assert.ok(['general','generated','booking'].includes(assets[key]),'Unclassified public asset: '+key);}
 assert.ok(statSync(resolve(publicRoot,'media/consultation-still-life.png')).size>0,'Checkpoint A hero is missing');
}
export function checkProtectedPaths(paths){
 const protectedPaths=paths.filter(path=>path.startsWith('appointment-system/')||path.startsWith('workers/')||path.startsWith('api/')||path.startsWith('backend/')||path.startsWith('.github/')||(path.startsWith('appointment-settings/')&&path!=='appointment-settings/public-assets.json')||['requirements.txt','pyproject.toml','vercel.json','package.json','package-lock.json','frontend/package-lock.json'].includes(path));
 assert.deepEqual(protectedPaths,[],'Protected backend or settings changed');
}
export function runChecks({root=resolve(import.meta.dirname,'../..'),baseline='fef4f4e48eb87fe748c9d05b3be3ce4f27f6a548'}={}){
 const frontend=resolve(root,'frontend'),assets=JSON.parse(readFileSync(resolve(root,'appointment-settings/public-assets.json')));
 checkAssets(assets,resolve(frontend,'public'));
 assert.equal(origin,'https://www.sarsajyotishsansthan.com');assert.equal(pages['/services'][0],'Consultations');assert.equal(Object.keys(pages).length,12);
 for(const path of Object.keys(pages))assert.ok(titleFor(path).endsWith(' | Sarsa Jyotish Sansthan'));
 // Compare the complete committed and working candidate with the approved start,
 // including new untracked files. HEAD-only comparison misses committed changes.
 const changed=execFileSync('git',['diff','--name-only',baseline],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const untracked=execFileSync('git',['ls-files','--others','--exclude-standard'],{cwd:root,encoding:'utf8'}).trim().split('\n');
 checkProtectedPaths([...changed,...untracked]);
 const source=listFiles(resolve(frontend,'src')).filter(p=>/\.(?:jsx?|mjs|tsx?)$/.test(p));
 assert.ok(source.length>20,'Unexpected working-source denominator');
 console.log(JSON.stringify({checks:'passed',public_routes:12,working_source_files:source.length,protected_diff:'unchanged',appearance:'checkpoint-A'}));
 return {source:source.map(p=>relative(frontend,p)),routes:Object.keys(pages)};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))runChecks();
