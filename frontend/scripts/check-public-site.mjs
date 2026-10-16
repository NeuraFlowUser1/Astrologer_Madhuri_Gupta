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
export function checkProtectedPaths(paths,approvedSettings=[]){
 const allowed=new Set(['appointment-settings/public-assets.json',...approvedSettings]);
 const protectedPaths=paths.filter(path=>path.startsWith('appointment-system/')||path.startsWith('workers/')||path.startsWith('api/')||path.startsWith('backend/')||path.startsWith('.github/')||(path.startsWith('appointment-settings/')&&!allowed.has(path))||['requirements.txt','pyproject.toml','vercel.json','package.json','package-lock.json','frontend/package-lock.json'].includes(path));
 assert.deepEqual(protectedPaths,[],'Protected backend or settings changed');
}
/** Permit only the approved addition/retirement, not arbitrary settings edits. */
function checkApprovedClientSettings(root,baseline){
 const read=path=>JSON.parse(readFileSync(resolve(root,path),'utf8'));
 const before=path=>JSON.parse(execFileSync('git',['show',`${baseline}:${path}`],{cwd:root,encoding:'utf8'}));
 const business='appointment-settings/business-settings.json',project='appointment-settings/project.json',hosting='appointment-settings/hosting-files.json',assets='appointment-settings/public-assets.json';
 const expectedBusiness=before(business);expectedBusiness.services.push({id:'prashna-kundali',name:'Prashna Kundali',enabled:true,pricing:{kind:'per_question',amount_paise:110000,maximum_questions:10},duration_minutes:30,required_preparation:[]});assert.deepEqual(read(business),expectedBusiness,'Unexpected business settings change');
 const expectedProject=before(project),index=expectedProject.surfaces.findIndex(s=>s.path==='/services/numerology');expectedProject.surfaces.splice(index+1,0,{path:'/services/prashna-kundali',class:'general'});assert.deepEqual(read(project),expectedProject,'Unexpected route/installation change');
 const retiredPublic=new Set(['/certificate.webp',...['jyotish-shastri','jyotish-acharya','astro-research-institute','trinity-vaastu-numerology'].flatMap(id=>['preview.webp','full.webp',`original.${id==='astro-research-institute'?'pdf':'jpeg'}`].map(suffix=>`/media/certificates/${id}-${suffix}`))]);
 const expectedAssets=Object.fromEntries(Object.entries(before(assets)).filter(([path])=>!retiredPublic.has(path)));assert.deepEqual(read(assets),expectedAssets,'Unexpected public asset classification change');
 const retired=new Set([...retiredPublic].map(path=>'frontend/public'+path));
 for(const file of ['Certifications.jsx','certificates-content.mjs','certifications.css','certifications-motion.mjs'])retired.add('frontend/src/site/'+file);
 retired.add('frontend/vitest.certifications.config.mjs');for(const file of ['certifications.html','certifications.jsx'])retired.add('frontend/tests/preview/'+file);
 for(const file of ['certifications-browser-review.js','certifications-layout.test.mjs','certifications-motion.test.mjs','certifications-page.test.jsx'])retired.add('frontend/tests/public-site/'+file);
 for(const file of ["frontend/src/components/Footer.jsx", "frontend/src/components/Navbar.jsx", "frontend/src/components/OurGoalSection.jsx", "frontend/src/components/ServicesSection.jsx", "frontend/src/components/TestimonialsSection.jsx", "frontend/src/components/VideoHeroCurtain.jsx", "frontend/src/components/motion-primitives/text-shimmer.tsx"])retired.add(file);
 const retainedModules=["about-layout.mjs", "BackToTop.jsx", "directory-motion.mjs", "home-enhancements.mjs", "MarginArt.jsx", "public-scroll.mjs", "service-media.css", "service-media.json", "service-visual-content.mjs", "service-visual-motion.mjs", "service-visual.css", "ServiceArtwork.jsx", "ServiceMedia.jsx", "ServiceVisualStory.jsx", "TestimonialReader.jsx", "testimonials-content.mjs", "testimonials-model.mjs", "testimonials-motion.mjs", "testimonials.css"].map(file=>'frontend/src/site/'+file);
 const retainedMedia=['kundli-matching','kundli-prediction','vastu-consultation','numerology'].flatMap(id=>[...[480,800,960,1200].map(width=>`frontend/src/site/media/services/${id}-primary-${width}.webp`),...[800,1200].map(width=>`frontend/src/site/media/services/${id}-supporting-${width}.webp`)]);
 const added=['frontend/src/pages/PrashnaKundali.jsx',...['PrashnaArtwork.jsx','prashna-content.mjs','prashna-motion.mjs','prashna.css'].map(file=>'frontend/src/site/'+file),...[480,800,960,1200].map(width=>`frontend/src/site/media/services/prashna-kundali-primary-${width}.webp`),...[800,1200].map(width=>`frontend/src/site/media/services/prashna-kundali-supporting-${width}.webp`)];
 const expectedHosting=before(hosting);expectedHosting.files=[...new Set([...expectedHosting.files.filter(path=>!retired.has(path)),...added,...retainedModules,...retainedMedia])].sort();assert.deepEqual(read(hosting),expectedHosting,'Unexpected hosting export change');
 return [business,project,hosting];
}
export function runChecks({root=resolve(import.meta.dirname,'../..'),baseline='7905f9b582c3712fbc33cb5e6d7ccfaeeba5888e'}={}){
 const frontend=resolve(root,'frontend'),assets=JSON.parse(readFileSync(resolve(root,'appointment-settings/public-assets.json')));
 checkAssets(assets,resolve(frontend,'public'));
 assert.equal(origin,'https://www.sarsajyotishsansthan.com');assert.equal(pages['/services'][0],'Services');assert.deepEqual(Object.keys(pages).sort(),['/','/about','/services','/testimonials','/services/kundli-prediction','/services/kundli-matching','/services/vastu-consultation','/services/numerology','/services/prashna-kundali','/booking/receipt','/booking-help','/booking','/contact','/privacy','/terms','/booking-policy'].sort());
 for(const path of Object.keys(pages))assert.ok(titleFor(path).endsWith(' | Sarsa Jyotish Sansthan'));
 // Compare the complete committed and working candidate with the approved start,
 // including new untracked files. HEAD-only comparison misses committed changes.
 const changed=execFileSync('git',['diff','--name-only',baseline],{cwd:root,encoding:'utf8'}).trim().split('\n');
 const untracked=execFileSync('git',['ls-files','--others','--exclude-standard'],{cwd:root,encoding:'utf8'}).trim().split('\n');
 checkProtectedPaths([...changed,...untracked],checkApprovedClientSettings(root,baseline));
 const source=listFiles(resolve(frontend,'src')).filter(p=>/\.(?:jsx?|mjs|tsx?)$/.test(p));
 assert.ok(source.length>20,'Unexpected working-source denominator');
 console.log(JSON.stringify({checks:'passed',public_routes:16,working_source_files:source.length,protected_diff:'unchanged-outside-approved-client-settings',appearance:'checkpoint-A-preserved-and-refined'}));
 return {source:source.map(p=>relative(frontend,p)),routes:Object.keys(pages)};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))runChecks();
