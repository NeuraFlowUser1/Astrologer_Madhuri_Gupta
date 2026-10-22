/** One public identity owner, shared by generated HTML and browser navigation. */
import {madhuriExperience,madhuriStudies} from './hero-content.mjs';
export const origin='https://www.sarsajyotishsansthan.com';
const brand='Sarsa Jyotish Sansthan';
export const shareImage=origin+'/media/sarsa-madhuri-share-20261022.webp';
export const shareAlt='Madhuri Gupta — Astro and Jyotish guidance at Sarsa Jyotish Sansthan, Agra';
const entry=(title,description,utility=false)=>Object.freeze({title:title+' | '+brand,description,utility});
export const pageRegistry=Object.freeze({
 '/':entry('Astrologer Madhuri Gupta in Agra','Explore Astro, Numerology and Vastu guidance with Madhuri Gupta at Sarsa Jyotish Sansthan in Agra. Read about the five services and contact the practice.'),
 '/about':entry('About Madhuri Gupta — Astro & Jyotish','Meet Madhuri Gupta, who leads Sarsa Jyotish Sansthan in Agra. Read about her 15+ years of experience, Jyotish studies and approach.'),
 '/services':entry('Astrology Services with Madhuri Gupta','Explore Kundli Prediction, Kundli Matching, Vastu, Numerology and Prashna Kundali services with Madhuri Gupta. Read about each service and contact the practice.'),
 '/services/kundli-prediction':entry('Kundli Prediction','Explore your birth chart and the questions you bring to a personal Kundli Prediction consultation with Madhuri Gupta.'),
 '/services/kundli-matching':entry('Kundli Matching','Bring your questions about compatibility to a personal Kundli Matching consultation with Madhuri Gupta.'),
 '/services/vastu-consultation':entry('Vastu Consultation','Discuss questions about your home or workspace in a Vastu consultation with Madhuri Gupta.'),
 '/services/prashna-kundali':entry('Prashna Kundali','Discuss a specific question with Madhuri through Prashna Kundali. Birth details are not required to book.'),
 '/services/numerology':entry('Numerology','Explore your questions about names and dates in a Numerology consultation with Madhuri Gupta.'),
 '/testimonials':entry('Customer Reviews','Customer feedback on Kundli, Vastu and Numerology consultations with Madhuri Gupta at Sarsa Jyotish Sansthan.'),
 '/contact':entry('Contact Madhuri Gupta in Agra',"Find Sarsa Jyotish Sansthan's contact details in Agra. Ask the practice a question or contact it for help with an existing appointment."),
 '/privacy':entry('Privacy Policy','How Sarsa Jyotish Sansthan handles booking and enquiry information, including practice and agency records.'),
 '/terms':entry('Terms of Service','Read the terms for consultations, booking and support at Sarsa Jyotish Sansthan.'),
 '/booking':entry('Book an appointment','Choose a consultation and an available appointment time with Madhuri Gupta. Online appointments use Google Meet.',true),
 '/booking/receipt':entry('View my booking','View your appointment details with the full name and phone number saved when booking.',true),
 '/booking-help':entry('View my booking','Open the booking-details page.',true),
 '/booking-policy':entry('Booking policy','Read the cancellation, rescheduling and refund rules for Sarsa Jyotish Sansthan consultations.',true),
});
export const publicPaths=Object.freeze(Object.keys(pageRegistry).filter(path=>!pageRegistry[path].utility));
// Existing app consumers read [short title, description]. Generation uses exact full titles.
export const pages=Object.freeze(Object.fromEntries(Object.entries(pageRegistry).map(([path,data])=>[path,[data.title.slice(0,-brand.length-3),data.description]])));
export const titleFor=path=>pageRegistry[path]?.title||'Page not found | '+brand;
export const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
export const safeJson=value=>JSON.stringify(value).replace(/[<>&\u2028\u2029]/g,char=>'\\u'+char.charCodeAt(0).toString(16).padStart(4,'0'));

export function metadataFor(path){
 const data=pageRegistry[path],privatePage=['/booking/receipt','/booking-help'].includes(path);
 return {title:titleFor(path),description:data?.description||'We could not find that page.',canonical:data&&!data.utility?origin+path:null,
  robots:data&&!data.utility?'index, follow':'noindex, nofollow',referrer:privatePage?'no-referrer':'strict-origin-when-cross-origin',image:shareImage,imageAlt:shareAlt};
}

/** Public facts only: no ratings, new accreditation, customer data or provider values. */
export function graphFor(path){
 if(!publicPaths.includes(path))return null;
 const data=metadataFor(path),business=origin+'/#practice',person=origin+'/#madhuri',website=origin+'/#website',page=origin+path+'#webpage';
 const graph=[
  {'@type':'Organization','@id':business,name:brand,url:origin+'/',email:'sarsajyotish@gmail.com',logo:origin+'/media/sarsa-kundli-lotus-logo-128.png',founder:{'@id':person},address:{'@type':'PostalAddress',streetAddress:'8, Gailana Road, LIC Colony',addressLocality:'Agra',addressRegion:'Uttar Pradesh',postalCode:'282007',addressCountry:'IN'}},
  {'@type':'Person','@id':person,name:'Madhuri Gupta',url:origin+'/about',image:origin+'/media/madhuri-gupta-portrait.jpeg',description:madhuriExperience+' years of experience in Astro and Jyotish guidance.',worksFor:{'@id':business},alumniOf:madhuriStudies.map(study=>({'@type':'EducationalOrganization',name:study.institute})),knowsAbout:['Jyotish','Kundli Prediction','Kundli Matching','Vastu','Numerology','Prashna Kundali']},
  {'@type':'WebSite','@id':website,name:brand,url:origin+'/',publisher:{'@id':business},inLanguage:'en'},
  {'@type':path==='/about'?'AboutPage':path==='/contact'?'ContactPage':'WebPage','@id':page,url:origin+path,name:data.title,description:data.description,isPartOf:{'@id':website},about:{'@id':path==='/about'?person:business},primaryImageOfPage:{'@type':'ImageObject',url:shareImage,caption:shareAlt},inLanguage:'en'},
 ];
 if(path.startsWith('/services/'))graph.push({'@type':'Service','@id':origin+path+'#service',name:pages[path][0],description:data.description,url:origin+path,provider:{'@id':business}});
 if(path!=='/'){
  const crumbs=[{name:'Home',url:origin+'/'}];
  if(path.startsWith('/services/'))crumbs.push({name:'Services',url:origin+'/services'});
  crumbs.push({name:pages[path][0],url:origin+path});
  graph.push({'@type':'BreadcrumbList','@id':origin+path+'#breadcrumbs',itemListElement:crumbs.map((item,index)=>({'@type':'ListItem',position:index+1,name:item.name,item:item.url}))});
 }
 return {'@context':'https://schema.org','@graph':graph};
}

function tagsFor(path){const meta=metadataFor(path);return [
 ['name','title',meta.title],['name','description',meta.description],['name','robots',meta.robots],['name','googlebot',meta.robots],['name','referrer',meta.referrer],
 ['property','og:title',meta.title],['property','og:description',meta.description],['property','og:url',meta.canonical||origin+path],['property','og:image',meta.image],['property','og:image:alt',meta.imageAlt],['property','og:image:width','1200'],['property','og:image:height','630'],['property','og:image:type','image/webp'],
 ['name','twitter:card','summary_large_image'],['name','twitter:title',meta.title],['name','twitter:description',meta.description],['name','twitter:url',meta.canonical||origin+path],['name','twitter:image',meta.image],['name','twitter:image:alt',meta.imageAlt],
 ];}

export function writePageMetadata(doc,path){
 const meta=metadataFor(path);doc.title=meta.title;
 for(const [attribute,key,value] of tagsFor(path)){
  const matches=[...doc.head.querySelectorAll(`meta[${attribute}="${key}"]`)];let element=matches.shift();matches.forEach(node=>node.remove());
  if(!element){element=doc.createElement('meta');element.setAttribute(attribute,key);doc.head.append(element);}element.setAttribute('content',value);
 }
 const canonicals=[...doc.head.querySelectorAll('link[rel="canonical"]')];let canonical=canonicals.shift();canonicals.forEach(node=>node.remove());
 if(!meta.canonical)canonical?.remove();else{if(!canonical){canonical=doc.createElement('link');canonical.rel='canonical';doc.head.append(canonical);}canonical.href=meta.canonical;}
 doc.head.querySelectorAll('script[type="application/ld+json"]').forEach(node=>node.remove());
 const graph=graphFor(path);if(graph){const script=doc.createElement('script');script.type='application/ld+json';script.dataset.sarsaGraph='';script.textContent=safeJson(graph);doc.head.append(script);}
}

export function renderMetadata(html,path){
 const meta=metadataFor(path),graph=graphFor(path);
 html=html.replace(/<title>[\s\S]*?<\/title>/g,'').replace(/<meta\s+(?:name|property)="(?:title|description|robots|googlebot|referrer|og:(?:title|description|url|image(?::alt|:width|:height|:type)?)|twitter:(?:card|title|description|url|image(?::alt|:width|:height|:type)?))"[^>]*>/g,'').replace(/<link\s+rel="canonical"[^>]*>/g,'').replace(/<script\s+type="application\/ld\+json"[^>]*>[\s\S]*?<\/script>/g,'');
 const head=`<title>${escapeHtml(meta.title)}</title>`+tagsFor(path).map(([attribute,key,value])=>`<meta ${attribute}="${key}" content="${escapeHtml(value)}">`).join('')+(meta.canonical?`<link rel="canonical" href="${escapeHtml(meta.canonical)}">`:'')+(graph?`<script type="application/ld+json" data-sarsa-graph>${safeJson(graph)}</script>`:'');
 return html.replace('</head>',head+'</head>');
}
