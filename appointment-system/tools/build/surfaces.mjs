/** Build the OFF boundary from actual bundle dependencies, not filename guesses. */
import {resolve,relative,sep} from 'node:path';
import {readdirSync,readFileSync,lstatSync,writeFileSync} from 'node:fs';

const safeFile=name=>typeof name==='string' && name.length>0 && !name.startsWith('/')
 && !/[\\?#%\u0000-\u001f\u007f]/.test(name) && name.split('/').every(part=>part && part!=='.' && part!=='..');
const modulePath=id=>id.split('?')[0].replaceAll('\\','/');
const dependencies=chunk=>[...(chunk.imports || []),...(chunk.dynamicImports || [])];

export function bundleSurfaces(bundle,bookingModules){
 if(!Array.isArray(bookingModules) || !bookingModules.length || new Set(bookingModules).size!==bookingModules.length)
  throw Error('Explicit exclusive booking modules are required.');
 const modules=new Set(bookingModules.map(modulePath)),roots=new Set(),matched=new Set();
 const chunks=Object.values(bundle).filter(item=>item.type==='chunk');
 for(const chunk of chunks){
  for(const id of Object.keys(chunk.modules || {}))if(modules.has(modulePath(id))){roots.add(chunk.fileName);matched.add(modulePath(id));}
 }
 if(matched.size!==modules.size)throw Error('A declared booking module was not found in the emitted bundle.');
 if(chunks.some(chunk=>chunk.isEntry && roots.has(chunk.fileName)))
  throw Error('Booking implementation is bundled into a general entry. Use a separate lazy import.');
 const walk=(starts,omitBooking)=>{
  const found=new Set(),pending=[...starts];
  while(pending.length){
   const name=pending.pop();if(found.has(name) || (omitBooking && roots.has(name)))continue;
   if(!safeFile(name) || !Object.hasOwn(bundle,name))throw Error('An emitted bundle dependency is missing.');
   found.add(name);const item=bundle[name];
   if(item.type==='chunk'){
    // A static dependency cannot be hidden while its importing general module
    // remains executable. Dynamic booking roots can safely stay unloaded OFF.
    if(omitBooking && (item.imports || []).some(dependency=>roots.has(dependency)))
     throw Error('General code statically imports an exclusive booking module.');
    pending.push(...dependencies(item),...(item.viteMetadata?.importedCss || []),...(item.viteMetadata?.importedAssets || []));
   }else if(name.endsWith('.css')){
    const css=typeof item.source==='string'?item.source:Buffer.from(item.source).toString('utf8');
    for(const match of css.matchAll(/url\(\s*(['"]?)(.*?)\1\s*\)/g)){
     const value=match[2].trim();if(!value || /^(?:data:|https?:|#|\/\/)/i.test(value))continue;
     const url=new URL(value,'https://bundle.invalid/'+name);
     if(url.origin!=='https://bundle.invalid' || url.search || url.hash)throw Error('Unclassified CSS asset address.');
     const asset=decodeURIComponent(url.pathname).slice(1);
     if(Object.hasOwn(bundle,asset))pending.push(asset);
     // Public-folder assets are classified separately from emitted assets.
    }
   }
  }
  return found;
 };
 const general=walk(chunks.filter(chunk=>chunk.isEntry).map(chunk=>chunk.fileName),true);
 const booking=walk(roots,false),assets={},unreferenced=[];
 for(const [name,item] of Object.entries(bundle)){
  if(!safeFile(name) || item.fileName!==name)throw Error('Invalid emitted filename.');
  if(name.endsWith('.html'))continue;
  if(name.endsWith('.map'))throw Error('Public source maps must not be emitted.');
  if(!general.has(name) && !booking.has(name)){
   // Vite can retain an emitted image after eliminating its unused import.
   // Keep an explicit record but do not make that orphan URL publicly servable.
   // Unowned executable/stylesheet output is still a build failure.
   if(item.type==='asset' && /\.(?:png|webp|jpe?g|gif|svg|ico|woff2?|ttf|mp4|webm|pdf)$/.test(name)
     && Array.isArray(item.originalFileNames) && item.originalFileNames.length){
    unreferenced.push({path:'/'+name,sources:item.originalFileNames});continue;
   }
   throw Error('An emitted asset has no classified dependency owner: '+name);
  }
  assets['/'+name]=general.has(name)?'general':'booking';
 }
 return {assets,booking_chunks:[...roots].sort(),shared_assets:[...general].filter(name=>booking.has(name)).sort(),unreferenced_assets:unreferenced};
}

export function surfaceManifestPlugin({bookingModules,evidenceFile='appointment-bundle-surfaces.json'}){
 let root;
 return {name:'contained-appointment-surfaces',enforce:'post',
  configResolved(config){root=config.root;},
  generateBundle(_options,bundle){
   const evidence=bundleSurfaces(bundle,bookingModules.map(path=>resolve(root,path)));
   this.emitFile({type:'asset',fileName:evidenceFile,source:JSON.stringify(evidence,null,2)+'\n'});
  }};
}

export function publicFiles(directory){
 const root=resolve(directory),files=[];
 function visit(path){
  if(lstatSync(path).isSymbolicLink())throw Error('Public asset links are forbidden.');
  for(const entry of readdirSync(path,{withFileTypes:true})){
   const child=resolve(path,entry.name);
   if(entry.isSymbolicLink())throw Error('Public asset links are forbidden.');
   if(entry.isDirectory())visit(child);
   else if(entry.isFile())files.push('/'+relative(root,child).split(sep).join('/'));
   else throw Error('Unexpected public asset type.');
  }
 }
 visit(root);return files.sort();
}

export function writeSurfaceManifest({dist,publicDirectory,project,publicPaths,bookingPaths,backendPaths,publicAssets}){
 const emitted=JSON.parse(readFileSync(resolve(dist,'appointment-bundle-surfaces.json'),'utf8'));
 const actual=publicFiles(publicDirectory);
 if(actual.join('\n')!==Object.keys(publicAssets).sort().join('\n'))
  throw Error('Every copied public file needs an explicit general/booking disposition.');
 const assets={...emitted.assets};
 for(const path of actual){
  if(!['booking','general','generated','not-served'].includes(publicAssets[path]) || Object.hasOwn(assets,path))throw Error('Public asset classification conflicts.');
  if(publicAssets[path]==='generated'){
   if(path!=='/sitemap.xml')throw Error('Only the declared sitemap is replaced by generated display variants.');
   continue;
  }
  if(publicAssets[path]==='not-served')continue;
  assets[path]=publicAssets[path];
 }
 const manifest={version:1,installation_id:project.installation_id,public_paths:publicPaths,
  booking_paths:bookingPaths,backend_paths:backendPaths,assets};
 writeFileSync(resolve(dist,'appointment-surface-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 return manifest;
}
