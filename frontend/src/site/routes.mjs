/** Only known legacy marketing routes are migrated; private data never enters links. */
const pages=new Set(['/','/about','/services','/booking','/contact','/testimonials','/privacy','/terms','/booking-policy',
 '/services/kundli-prediction','/services/kundli-matching','/services/vastu-consultation','/services/numerology']);
const services=new Set(['kundli-prediction','kundli-matching','vastu-consultation','numerology']);
export function legacyDestination(hash){
 if(typeof hash!=='string'||!hash.startsWith('#/')||hash.startsWith('#//'))return null;
 let url;try{url=new URL(hash.slice(1),'https://sarsa.invalid');}catch{return null;}
 if(url.origin!=='https://sarsa.invalid'||!pages.has(url.pathname))return null;
 const query=new URLSearchParams();
 if(url.pathname==='/booking'&&services.has(url.searchParams.get('service')))query.set('service',url.searchParams.get('service'));
 const anchor=/^#[a-z][a-z0-9-]{0,63}$/.test(url.hash)?url.hash:'';
 return url.pathname+(query.size?'?'+query.toString():'')+anchor;
}
export function migrateLegacyLocation(location,history){
 if(location.pathname!=='/')return;
 const destination=legacyDestination(location.hash);
 if(destination!==null)history.replaceState(history.state,'',destination);
}
