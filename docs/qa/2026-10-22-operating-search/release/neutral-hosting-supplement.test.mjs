/** Disconnected supplemental contracts; imports the unchanged measured copy only. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,cpSync,symlinkSync,rmSync,chmodSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join,delimiter} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=process.env.NEUTRAL_MEASUREMENT_ROOT,manifest=JSON.parse(readFileSync(join(root,'manifest.json'))),copy=manifest.copy;
const load=path=>import(pathToFileURL(join(copy,path)));
const {bundleSurfaces,publicFiles,writeSurfaceManifest}=await load('tools/build/surfaces.mjs');
const {generateModes}=await load('tools/build/page-modes.mjs');
const {normalizedPath,classify}=await load('hosting/surface-policy.mjs');
const {readProjection,checkedManifest,createRouting}=await load('hosting/routing.mjs');
const {facts}=await load('worker/installation.mjs');
const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'example-practice',environment:'test',origin:'https://practice.example.test',aliases:[],worker:{origin:'https://worker.example.test'},surfaces:[{path:'/',class:'general'}]};
const surface={version:1,installation_id:project.installation_id,public_paths:['/'],booking_paths:['/booking'],backend_paths:[],assets:{}};
const temporary=operation=>{const path=mkdtempSync(join(tmpdir(),'neutral-hosting-contract-'));try{return operation(path);}finally{rmSync(path,{recursive:true,force:true});}};
const chunk=(fileName,module,options={})=>({type:'chunk',fileName,modules:{[module]:{}},...options});
const asset=(fileName,source)=>({type:'asset',fileName,source});

test('bundle traces minimal chunks, missing optional metadata and intentionally external CSS addresses',()=>{
 const bundle={
  'site.js':chunk('site.js','site',{isEntry:true,dynamicImports:['booking.js'],imports:['general.css']}),
  'booking.js':chunk('booking.js','book'),
  'general.css':asset('general.css','a{background:url("")}b{background:url(#mask)}c{background:url(//cdn.example/x)}d{background:url(./public-only.svg)}'),
 };
 assert.equal(bundleSurfaces(bundle,['book']).assets['/general.css'],'general');
 const noModules={...bundle,'empty.js':{type:'chunk',fileName:'empty.js'}};noModules['site.js']={...noModules['site.js'],dynamicImports:['booking.js','empty.js']};
 assert.equal(bundleSurfaces(noModules,['book']).assets['/empty.js'],'general');
 assert.equal(bundleSurfaces({...bundle,'booking.js':chunk('booking.js','book',{imports:['shared.js']}),'shared.js':chunk('shared.js','shared')},['book']).assets['/shared.js'],'booking');
});

test('public classifier chooses the longest nested prefix and normalises empty html names',()=>{
 const surfaces=[{path:'/',class:'general'},{path:'/information',class:'enquiry'},{path:'/information/appointments',class:'booking'}];
 assert.equal(classify('/information/appointments/one',surfaces),'booking');
 assert.equal(classify('/information/questions',surfaces),'enquiry');
 assert.equal(normalizedPath('/.html'),'/');
 assert.equal(normalizedPath('/INDEX.HTML'),'/');
 for(const invalid of [null,12,{},'/a/./b','/a/../b'])assert.throws(()=>normalizedPath(invalid),/invalid_address/);
});

test('public manifest handles only the declared generated sitemap and explicitly withheld files',()=>temporary(path=>{
 const dist=join(path,'dist'),pub=join(path,'public');mkdirSync(dist);mkdirSync(pub);
 writeFileSync(join(dist,'appointment-bundle-surfaces.json'),JSON.stringify({assets:{'/bundle.js':'general'}}));
 for(const name of ['sitemap.xml','withheld.pdf','ordinary.txt'])writeFileSync(join(pub,name),'local fixture');
 const input={dist,publicDirectory:pub,project,publicPaths:['/'],bookingPaths:['/booking'],backendPaths:[],publicAssets:{'/sitemap.xml':'generated','/withheld.pdf':'not-served','/ordinary.txt':'general'}};
 const result=writeSurfaceManifest(input);assert.equal(result.assets['/ordinary.txt'],'general');assert(!Object.hasOwn(result.assets,'/sitemap.xml'));assert(!Object.hasOwn(result.assets,'/withheld.pdf'));
 assert.throws(()=>writeSurfaceManifest({...input,publicAssets:{...input.publicAssets,'/ordinary.txt':'generated'}}),/Only the declared sitemap/);
 writeFileSync(join(pub,'bundle.js'),'conflict');assert.throws(()=>writeSurfaceManifest({...input,publicAssets:{...input.publicAssets,'/bundle.js':'general'}}),/classification conflicts/);
 const link=join(path,'linked-root');symlinkSync(pub,link);assert.throws(()=>publicFiles(link),/links are forbidden/);
 const special=join(pub,'pipe');const made=spawnSync('mkfifo',[special]);assert.equal(made.status,0);assert.throws(()=>publicFiles(pub),/Unexpected public asset type/);
}));

test('page generation rejects a non-callable renderer before writing any page',()=>temporary(dist=>{
 assert.throws(()=>generateModes({dist,shell:'<head></head><body></body>',pages:{'/':['Home','Description']},project,manifest:surface,brand:'Fixture',renderPage:{}}),/renderer must be a function/);
}));

test('routing refuses noncanonical keys and null JSON streams without a provider call',async()=>{
 const valid=Buffer.alloc(32,19).toString('base64url')+'=';
 const noncanonical=valid.slice(0,-2)+(valid.at(-2)==='B'?'C':'B')+'=';
 let calls=0;await assert.rejects(readProjection(project,{environment:{BOOKING_CONTROL_READ_KEY:noncanonical},fetcher:async()=>{calls++;return Response.json({});}}),/state_configuration/);assert.equal(calls,0);
 await assert.rejects(readProjection(project,{environment:{BOOKING_CONTROL_READ_KEY:valid},fetcher:async()=>new Response(null,{headers:{'content-type':'application/json'}})}),/state_invalid/);
});

test('manifest bounds and explicit company/provider/worker surfaces stay behind host authentication',async()=>{
 for(const copy of [{...surface,public_paths:{}},{...surface,public_paths:Array(1001).fill('/')}])assert.throws(()=>checkedManifest(copy,project),/surface_manifest_invalid/);
 assert.throws(()=>checkedManifest(surface,{...project,aliases:[project.origin,project.origin]}),/surface_manifest_invalid/);
 const declared={...project,surfaces:[...project.surfaces,{path:'/operator',class:'company'},{path:'/delivery',class:'provider'},{path:'/queue-control',class:'worker'}]};
 let calls=0;const route=createRouting({project:declared,manifest:surface,next:()=>{calls++;return new Response('authenticated backend');},rewrite:()=>{throw Error('unexpected public rewrite');},fetcher:()=>{throw Error('No state read for independently authenticated work');}});
 for(const path of ['/operator','/delivery','/queue-control','/api']){const response=await route(new Request(project.origin+path));assert.equal(await response.text(),'authenticated backend');}
 assert.equal(calls,4);
});

test('installation validates parse failures, exact origin and allowed test loopback independently',()=>{
 const environment={BOOKING_INSTALLATION_ID:project.installation_id,BOOKING_PROJECT_ID:'fixture',BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'http://localhost'};
 assert.equal(facts(environment).origin,'http://localhost');assert.equal(facts({...environment,BOOKING_PUBLIC_ORIGIN:'http://127.0.0.1'}).origin,'http://127.0.0.1');
 for(const value of ['not-a-url','https://example.test/path','https://example.test?x=1','http://remote.example.test'])assert.throws(()=>facts({...environment,BOOKING_PUBLIC_ORIGIN:value}),/state_configuration/);
 assert.throws(()=>facts({...environment,BOOKING_ENVIRONMENT:'production'}),/state_configuration/);
});

test('installed source CLI forwards exact local root and Python contract; failures preserve nonzero status',()=>temporary(path=>{
 const installation=join(path,'appointment-system'),entry=join(installation,'tools/install/source.mjs');mkdirSync(join(installation,'tools/install'),{recursive:true});
 cpSync(join(copy,'tools/install/source.mjs'),entry);
 const python=join(path,'fixture-python');writeFileSync(python,'#!/usr/bin/python3\nimport sys,os,json,signal\nprint(json.dumps({"args":sys.argv[1:],"pythonpath":os.environ["PYTHONPATH"],"bytecode":os.environ["PYTHONDONTWRITEBYTECODE"]}),flush=True)\nif os.environ.get("FIXTURE_SIGNAL"): os.kill(os.getpid(),signal.SIGTERM)\nsys.exit(int(os.environ.get("FIXTURE_EXIT","0")))\n');chmodSync(python,0o700);
 const preload=process.env.NEUTRAL_MEASUREMENT_PRELOAD;
 const run=(file,extra={})=>spawnSync(process.execPath,['--import',preload,file],{cwd:path,env:{...process.env,BOOKING_SETUP_PYTHON:python,...extra},encoding:'utf8'});
 let result=run(entry);assert.equal(result.status,0);const data=JSON.parse(result.stdout.trim());assert.deepEqual(data.args,['-m','tools.install.source',path,'--expected-root',path]);assert.equal(data.pythonpath,[installation,join(installation,'engine')].join(delimiter));assert.equal(data.bytecode,'1');
 result=run(entry,{FIXTURE_EXIT:'7'});assert.equal(result.status,7);
 result=run(entry,{FIXTURE_SIGNAL:'1'});assert.equal(result.status,1);
 result=run(entry,{BOOKING_SETUP_PYTHON:join(path,'not-present')});assert.equal(result.status,1);assert.match(result.stderr,/Select a Python environment/);
 result=run(join(copy,'tools/install/source.mjs'));assert.notEqual(result.status,0);assert.match(result.stderr,/installed project copy/);
}));
