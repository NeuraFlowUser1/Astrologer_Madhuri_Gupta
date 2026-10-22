/** Disconnected QA only: instrument unchanged app source into an ignored local build. */
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';
import {createInstrumenter} from 'istanbul-lib-instrument';
import {mkdir,writeFile} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {publicPaths} from '../../src/site/page-metadata.mjs';
const root=resolve(import.meta.dirname,'../..'),output=resolve(root,'coverage/operating-browser');
const fingerprints={};
const instrumenter=createInstrumenter({esModules:true,produceSourceMap:true,parserPlugins:['jsx'],coverageVariable:'__sarsaCoverage__',coverageGlobalScope:'globalThis',coverageGlobalScopeFunc:false});
function instrument(){return {name:'local-source-coverage-only',enforce:'pre',transform(code,id){const file=id.split('?')[0];if(!file.startsWith(root+'/src/')||! /\.(?:mjs|js|jsx)$/.test(file))return;const original=readFileSync(file,'utf8');assert.equal(code,original,'Instrument original source before transforms: '+file);fingerprints[file]=createHash('sha256').update(original).digest('hex');return {code:instrumenter.instrumentSync(original,file),map:instrumenter.lastSourceMap()};}};}
const plugins=()=>[instrument(),react(),tailwind()];
await build({root,configFile:false,plugins:plugins(),build:{outDir:resolve(output,'client'),emptyOutDir:true,minify:false}});
await build({root,configFile:false,plugins:plugins(),build:{ssr:resolve(root,'src/render-public.jsx'),outDir:resolve(output,'ssr'),emptyOutDir:true,copyPublicDir:false,minify:false,rollupOptions:{output:{entryFileNames:'render.mjs'}}}});
const previous=globalThis.fetch;globalThis.fetch=()=>{throw Error('Server public rendering must not call a provider');};
try{
 const {renderPublicPage}=await import(pathToFileURL(resolve(output,'ssr/render.mjs')));
 let documents=0;
 for(const mode of ['on','off'])for(const path of publicPaths){const html=renderPublicPage(path,mode);assert.equal((html.match(/<h1(?:\s|>)/g)||[]).length,1);assert(!html.includes('Loading the page…'));if(path==='/contact')assert(/<fieldset[^>]*disabled/.test(html));documents++;}
 assert.throws(()=>renderPublicPage('/booking','on'),/reviewed public routes/);assert.throws(()=>renderPublicPage('/','unknown'),/reviewed public routes/);
 await mkdir(output,{recursive:true});await writeFile(resolve(output,'source-fingerprints.json'),JSON.stringify(fingerprints));await writeFile(resolve(output,'server-coverage.json'),JSON.stringify(globalThis.__sarsaCoverage__));
 console.log(JSON.stringify({source:'actual unchanged public renderer',documents,privateRefused:true,networkRefused:true,output}));
}finally{globalThis.fetch=previous;}
