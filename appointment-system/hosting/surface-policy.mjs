import policy from '../contracts/surfaces.json' with {type:'json'};

export const within=(path,prefix)=>path===prefix || path.startsWith(prefix.replace(/\/$/,'')+'/');

// Input has already been URL-decoded once, exactly as in the Python guard.
export function normalizedPath(path){
 if(typeof path!=='string' || !path.startsWith('/') || /[\\%?#\u0000-\u001f\u007f]/.test(path)
   || path.split('/').some(part=>part==='.' || part==='..'))throw Error('invalid_address');
 path='/'+path.toLowerCase().split('/').filter(Boolean).join('/');
 if(path.endsWith('/index.html'))return path.slice(0,-11) || '/';
 return path.endsWith('.html') ? path.slice(0,-5) || '/':path;
}

export function classify(path,surfaces){
 path=normalizedPath(path);
 if(policy.protected_exact.includes(path) || policy.protected_prefixes.some(prefix=>within(path,prefix)))return 'private';
 if(policy.booking_prefixes.some(prefix=>within(path,prefix)))return 'booking';
 const exact=surfaces.find(item=>item.path.toLowerCase()===path);
 if(exact)return exact.class;
 return surfaces.filter(item=>item.path!=='/' && within(path,item.path.toLowerCase()))
   .sort((a,b)=>b.path.length-a.path.length)[0]?.class || 'general';
}
