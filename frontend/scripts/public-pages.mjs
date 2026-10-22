/** Render the actual public components in both display modes, without live reads. */
import {readFileSync,writeFileSync,existsSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'vite';
import {pageRegistry,publicPaths,renderMetadata} from '../src/site/page-metadata.mjs';
import project from '../../appointment-settings/project.json' with {type:'json'};
import publicAssets from '../../appointment-settings/public-assets.json' with {type:'json'};
import {generateModes} from '../../appointment-system/tools/build/page-modes.mjs';
import {writeSurfaceManifest} from '../../appointment-system/tools/build/surfaces.mjs';
const frontend=resolve(import.meta.dirname,'..'),dist=resolve(frontend,'dist'),serverOutput=resolve(frontend,'dist-ssr');
const bookingPaths=Object.keys(pageRegistry).filter(path=>pageRegistry[path].utility);
const manifest=writeSurfaceManifest({dist,publicDirectory:resolve(frontend,'public'),project,publicPaths,bookingPaths,
 backendPaths:['/studio','/studio/calendar','/enquiries-studio'],publicAssets});
const shell=readFileSync(resolve(dist,'index.html'),'utf8').replace(/<meta name="booking-display-mode" content="(?:on|off)">/g,'').replace(/<noscript data-sarsa-static>[\s\S]*?<\/noscript>/g,'').replace(/<div id="root"(?:\s[^>]*)?>[\s\S]*<\/div>\s*(?=<\/body>)/,'<div id="root"></div>');
try{
 await build({root:frontend,configFile:resolve(frontend,'vite.config.js'),build:{ssr:resolve(frontend,'src/render-public.jsx'),outDir:serverOutput,emptyOutDir:true,copyPublicDir:false,minify:false,rollupOptions:{output:{entryFileNames:'render-public.mjs'}}}});
 const {renderPublicPage}=await import(pathToFileURL(resolve(serverOutput,'render-public.mjs')).href);
 const rendered=new Map();for(const mode of ['on','off'])for(const path of publicPaths)rendered.set(mode+path,renderPublicPage(path,mode));
 generateModes({dist,shell,pages:pageRegistry,project,manifest,brand:project.label,renderPage:({path,mode,booking,html})=>{
  const content=booking?'':rendered.get(mode+path);
  if(!booking&&!content)throw Error('Missing actual public HTML: '+path);
  const marker=booking?'':` data-public-path="${path}" data-public-mode="${mode}" data-public-render="sarsa-public-v1"`;
  const target=/<div id="root">[\s\S]*?<\/div>/;
  if(!target.test(html))throw Error('Expected a single empty client root before generation.');
  return renderMetadata(html.replace(target,()=>'<div id="root"'+marker+'>'+content+'</div>'),path);
 }});
 // The neutral generator enforces a canonical after its renderer callback.
 // Booking utilities keep the receiving registry's noindex/no-canonical policy
 // in the actual delivered files too, before any browser code can run.
 for(const path of bookingPaths){
  const relative=path.slice(1)+'.html';
  for(const file of [resolve(dist,relative),resolve(dist,'__booking_display/on',relative)]){
   writeFileSync(file,renderMetadata(readFileSync(file,'utf8'),path));
  }
  if(existsSync(resolve(dist,'__booking_display/off',relative)))throw Error('Booking utility must remain withheld while OFF: '+path);
 }
}finally{rmSync(serverOutput,{recursive:true,force:true});}
console.log('Generated 12 actual public pages in both display modes; booking utilities remain excluded.');
