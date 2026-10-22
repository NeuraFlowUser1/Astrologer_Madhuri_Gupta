/** Read-only Sarsa release preflight. No provider settings or customer writes. */
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,statSync} from 'node:fs';
import {resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {pages,origin,titleFor,publicPaths} from '../src/site/page-metadata.mjs';

export function listFiles(root){return readdirSync(root,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?listFiles(resolve(root,entry.name)):[resolve(root,entry.name)]);}
export function checkAssets(assets,publicRoot){
 for(const path of listFiles(publicRoot)){const key='/'+relative(publicRoot,path).replaceAll('\\','/');assert.ok(['general','generated','booking'].includes(assets[key]),'Unclassified public asset: '+key);}
 assert.ok(statSync(resolve(publicRoot,'media/consultation-still-life.png')).size>0,'Checkpoint A hero is missing');
}
export function checkProtectedPaths(paths,approvedSettings=[]){
 const allowed=new Set(['appointment-settings/public-assets.json',...approvedSettings]);
 const protectedPaths=paths.filter(path=>!allowed.has(path)&&(path.startsWith('appointment-system/')||path.startsWith('workers/')||path.startsWith('api/')||path.startsWith('backend/')||path.startsWith('.github/')||(path.startsWith('appointment-settings/')&&!allowed.has(path))||['requirements.txt','pyproject.toml','vercel.json','package.json','package-lock.json','frontend/package-lock.json'].includes(path)));
 assert.deepEqual(protectedPaths,[],'Protected backend or settings changed');
}
/** Reviewed programme checkpoint. Earlier Prashna checks are dated history. */
const approvedRelease='1bb6cb1cc00a2ead7cec70de052ea78330005d7644dfc0d2e2a40ea7c287b31f';
const addedMedia=[768,1280,1920].map(width=>`/media/consultation-still-life-${width}.webp`).concat('/media/sarsa-madhuri-share-20261022.webp');
const addedHosting=['frontend/src/render-public.jsx','frontend/src/site/about-portrait.mjs','frontend/src/site/brand.css','frontend/src/site/hero-band-motion.mjs','frontend/src/site/hero-content.mjs','frontend/src/site/hero-refinement.css','frontend/src/site/HeroDetails.jsx','frontend/scripts/check-public-site.mjs','frontend/public/media/sarsa-kundli-lotus-favicon.png','frontend/public/media/sarsa-kundli-lotus-logo-128.png',...addedMedia.map(path=>'frontend/public'+path)];
function checkApprovedClientSettings(root,baseline){
 const read=path=>JSON.parse(readFileSync(resolve(root,path),'utf8'));
 const before=path=>JSON.parse(execFileSync('git',['show',`${baseline}:${path}`],{cwd:root,encoding:'utf8'}));
 for(const name of ['business-settings','project','booking-browser','enquiry-browser','staff-browser']){
  const path=`appointment-settings/${name}.json`;assert.deepEqual(read(path),before(path),'Unapproved installation, business or browser policy change: '+path);
 }
 const assets='appointment-settings/public-assets.json',expectedAssets=before(assets);for(const path of addedMedia)expectedAssets[path]='general';assert.deepEqual(read(assets),expectedAssets,'Unexpected public asset classification change');
 const hosting='appointment-settings/hosting-files.json',expectedHosting=before(hosting);expectedHosting.files=[...new Set([...expectedHosting.files.filter(path=>path!=='frontend/scripts/hero-static.mjs'),...addedHosting])].sort();assert.deepEqual(read(hosting),expectedHosting,'Unexpected hosting export change');
 const exported=new Set(read(hosting).files);for(const file of listFiles(resolve(root,'frontend/src')))assert.ok(exported.has(relative(root,file).replaceAll('\\','/')),'A required source file is absent from the official hosting export: '+file);
 const worker='workers/booking-recovery/wrangler.json',expectedWorker=before(worker);expectedWorker.vars.BOOKING_RELEASE_DIGEST=approvedRelease;assert.deepEqual(read(worker),expectedWorker,'Unexpected owned worker configuration change');
 return [assets,hosting,worker];
}
function checkContainedRelease(root){
 const packageRoot=resolve(root,'appointment-system');
 // The package's own verifier checks its complete inventory, all hashes, digest,
 // runtime contracts and forbidden symlinks. Do not trust a copied label alone.
 const verifyScript="import json,sys; from pathlib import Path; p=Path(sys.argv[1]); sys.path.insert(0,str(p)); from tools.install.package import verify; r=verify(p); print(json.dumps({'release':r['release'],'digest':r['content_digest'],'files':len(r['files'])}))";
 const checked=JSON.parse(execFileSync('python3',['-c',verifyScript,packageRoot],{encoding:'utf8'}));
 assert.equal(checked.release,'1.0.1-rc.3');assert.equal(checked.digest,approvedRelease);assert.equal(checked.files,579);
 const release=JSON.parse(readFileSync(resolve(packageRoot,'release.json'),'utf8'));
 return new Set(['appointment-system/release.json',...Object.keys(release.files).map(path=>'appointment-system/'+path)]);
}
export function runChecks({root=resolve(import.meta.dirname,'../..'),baseline='7f6fc4eddc4b67a3265329a13696d2be488613b7'}={}){
 const frontend=resolve(root,'frontend'),assets=JSON.parse(readFileSync(resolve(root,'appointment-settings/public-assets.json')));
 checkAssets(assets,resolve(frontend,'public'));
 assert.equal(origin,'https://www.sarsajyotishsansthan.com');assert.equal(pages['/services'][0],'Astrology Services with Madhuri Gupta');assert.deepEqual(Object.keys(pages).sort(),['/','/about','/services','/testimonials','/services/kundli-prediction','/services/kundli-matching','/services/vastu-consultation','/services/numerology','/services/prashna-kundali','/booking/receipt','/booking-help','/booking','/contact','/privacy','/terms','/booking-policy'].sort());
 for(const path of Object.keys(pages))assert.ok(titleFor(path).endsWith(' | Sarsa Jyotish Sansthan'));
 // Compare the complete committed and working candidate with the approved start,
 // including new untracked files. HEAD-only comparison misses committed changes.
 const changed=execFileSync('git',['diff','--name-only',baseline],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const untracked=execFileSync('git',['ls-files','--others','--exclude-standard'],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const verifiedPackage=checkContainedRelease(root);
 checkProtectedPaths([...changed,...untracked].filter(path=>!verifiedPackage.has(path)),checkApprovedClientSettings(root,baseline));
 const source=listFiles(resolve(frontend,'src')).filter(p=>/\.(?:jsx?|mjs|tsx?)$/.test(p));
 assert.ok(source.length>20,'Unexpected working-source denominator');
 console.log(JSON.stringify({checks:'passed',ordinary_public_routes:publicPaths.length,booking_utilities:4,total_routes:16,working_source_files:source.length,protected_diff:'unchanged-outside-approved-client-settings',appearance:'approved-pages-preserved-with-operating-search-refinements',contained_release:'1.0.1-rc.3',contained_digest:approvedRelease}));
 return {source:source.map(p=>relative(frontend,p)),routes:Object.keys(pages)};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))runChecks();
