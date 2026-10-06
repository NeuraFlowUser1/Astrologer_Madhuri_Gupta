import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,symlinkSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {bundleSurfaces,surfaceManifestPlugin,publicFiles,writeSurfaceManifest} from '../tools/build/surfaces.mjs';

const chunk=(fileName,module,{imports=[],dynamicImports=[],entry=false,css=[],assets=[]}={})=>({type:'chunk',fileName,isEntry:entry,
 modules:{[module]:{}},imports,dynamicImports,viteMetadata:{importedCss:new Set(css),importedAssets:new Set(assets)}});
const asset=(fileName,source='bytes')=>({type:'asset',fileName,source});
function bundle(){return {
 'assets/site.js':chunk('assets/site.js','/site/src/App.jsx',{entry:true,imports:['assets/react.js'],dynamicImports:['assets/booking.js','assets/contact.js']}),
 'assets/react.js':chunk('assets/react.js','react'),
 'assets/contact.js':chunk('assets/contact.js','/site/src/Contact.jsx',{imports:['assets/react.js','assets/form.js']}),
 'assets/booking.js':chunk('assets/booking.js','/site/src/Booking.jsx',{imports:['assets/react.js','assets/form.js'],css:['assets/booking.css'],assets:['assets/guide.webp']}),
 'assets/form.js':chunk('assets/form.js','/site/src/Form.jsx'),
 'assets/booking.css':asset('assets/booking.css','body{background:url("./diagram.svg");font-family:Test}'),
 'assets/diagram.svg':asset('assets/diagram.svg'), 'assets/guide.webp':asset('assets/guide.webp'), 'index.html':asset('index.html')};}
const modules=['/site/src/Booking.jsx'];

test('actual import graph isolates booking code, CSS and media while preserving shared forms/framework',()=>{
 const result=bundleSurfaces(bundle(),modules);
 for(const name of ['booking.js','booking.css','diagram.svg','guide.webp'])assert.equal(result.assets['/assets/'+name],'booking');
 for(const name of ['site.js','contact.js','react.js','form.js'])assert.equal(result.assets['/assets/'+name],'general');
 assert.deepEqual(result.shared_assets,['assets/form.js','assets/react.js']);
 assert.deepEqual(result.booking_chunks,['assets/booking.js']);assert.equal(result.assets['/index.html'],undefined);
});

test('build refuses a booking page merged into the entry or statically needed by ordinary code',()=>{
 let copy=bundle();copy['assets/site.js'].modules['/site/src/Booking.jsx']={};assert.throws(()=>bundleSurfaces(copy,modules),/general entry/);
 copy=bundle();copy['assets/contact.js'].imports.push('assets/booking.js');assert.throws(()=>bundleSurfaces(copy,modules),/statically imports/);
});

test('a media file left behind by an eliminated import is recorded but never made public',()=>{
 const copy=bundle();copy['assets/unused.webp']={...asset('assets/unused.webp'),originalFileNames:['src/unused.webp']};
 const result=bundleSurfaces(copy,modules);assert.equal(result.assets['/assets/unused.webp'],undefined);
 assert.deepEqual(result.unreferenced_assets,[{path:'/assets/unused.webp',sources:['src/unused.webp']}]);
 copy['assets/unknown.png']=asset('assets/unknown.png');assert.throws(()=>bundleSurfaces(copy,modules));
});

test('missing imports, undeclared roots, unowned output and source maps fail the build',()=>{
 for(const change of [b=>b['assets/site.js'].imports.push('missing.js'),b=>b['assets/orphan.js']=chunk('assets/orphan.js','orphan'),
  b=>b['assets/booking.js.map']=asset('assets/booking.js.map'),b=>b['../outside']=asset('../outside'),
  b=>b['assets/react.js'].fileName='other.js']){const copy=bundle();change(copy);assert.throws(()=>bundleSurfaces(copy,modules));}
 for(const roots of [[],['/not-present.jsx'],[...modules,...modules]])assert.throws(()=>bundleSurfaces(bundle(),roots));
});

test('CSS dependencies are traced and ambiguous asset parameters are refused',()=>{
 const copy=bundle();copy['assets/booking.css'].source=Buffer.from('a{background:url(data:image/x,abc)}b{background:url(https://external.example/x)}c{background:url(./diagram.svg)}');
 assert.equal(bundleSurfaces(copy,modules).assets['/assets/diagram.svg'],'booking');
 copy['assets/booking.css'].source='a{background:url(./diagram.svg?other=1)}';assert.throws(()=>bundleSurfaces(copy,modules));
});

test('Vite plugin resolves declared project modules and emits evidence only after checking the bundle',()=>{
 const plugin=surfaceManifestPlugin({bookingModules:['src/Booking.jsx']});let emitted;
 plugin.configResolved({root:'/site'});plugin.generateBundle.call({emitFile:value=>emitted=value},{},bundle());
 assert.equal(emitted.fileName,'appointment-bundle-surfaces.json');assert.equal(JSON.parse(emitted.source).assets['/assets/booking.js'],'booking');
});

test('all copied public files need a reviewed disposition and symlinks are rejected',()=>{
 const root=mkdtempSync(join(tmpdir(),'abs-build-surfaces-'));
 try{
  const dist=join(root,'dist'),publicDirectory=join(root,'public');mkdirSync(dist);mkdirSync(publicDirectory);mkdirSync(join(publicDirectory,'media'));
  writeFileSync(join(publicDirectory,'media','portrait.webp'),'portrait');writeFileSync(join(publicDirectory,'guide.pdf'),'booking guide');
  writeFileSync(join(dist,'appointment-bundle-surfaces.json'),JSON.stringify(bundleSurfaces(bundle(),modules)));
  assert.deepEqual(publicFiles(publicDirectory),['/guide.pdf','/media/portrait.webp']);
  const input={dist,publicDirectory,project:{installation_id:'fixture'},publicPaths:['/'],bookingPaths:['/booking'],backendPaths:['/company'],
   publicAssets:{'/guide.pdf':'booking','/media/portrait.webp':'general'}};
  const result=writeSurfaceManifest(input);assert.equal(result.assets['/guide.pdf'],'booking');
  assert.deepEqual(JSON.parse(readFileSync(join(dist,'appointment-surface-manifest.json'),'utf8')),result);
  assert.throws(()=>writeSurfaceManifest({...input,publicAssets:{'/guide.pdf':'booking'}}));
  assert.throws(()=>writeSurfaceManifest({...input,publicAssets:{...input.publicAssets,'/guide.pdf':'unknown'}}));
  symlinkSync(join(publicDirectory,'guide.pdf'),join(publicDirectory,'linked.pdf'));assert.throws(()=>publicFiles(publicDirectory));
 }finally{rmSync(root,{recursive:true,force:true});}
});
