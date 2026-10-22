/** Test-only native coverage: original source identities, captured on process exit. */
import {registerHooks} from 'node:module';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInstrumenter} from 'istanbul-lib-instrument';
const root=resolve(import.meta.dirname,'../..');
const files=['src/site/routes.mjs','scripts/public-pages.mjs','src/site/page-metadata.mjs','src/site/about-portrait.mjs'].map(file=>resolve(root,file));
const instrumenter=createInstrumenter({esModules:true,coverageVariable:'__sarsaCoverage__',coverageGlobalScope:'globalThis',coverageGlobalScopeFunc:false});
registerHooks({load(url,context,next){
 if(url.endsWith('.json')&&!context.importAttributes?.type)context={...context,importAttributes:{...context.importAttributes,type:'json'}};
 const result=next(url,context);if(url.startsWith('file:')){const path=fileURLToPath(url);if(files.includes(path))return {...result,source:instrumenter.instrumentSync(readFileSync(path,'utf8'),path)};}return result;
}});
process.on('exit',()=>{const output=resolve(root,process.env.SARSA_NATIVE_COVERAGE||'coverage/operating-browser/native-source-coverage.json');if(!output.startsWith(root+'/coverage/'))throw Error('Coverage is restricted to ignored local QA output');mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(globalThis.__sarsaCoverage__||{}));});
