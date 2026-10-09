/** Test-only synthetic contracts. Never proxies an application/provider request. */
import {readFileSync} from 'node:fs';
export const business=JSON.parse(readFileSync(new URL('../../../appointment-settings/business-settings.json',import.meta.url)));
export const viewports=[[320,740],[390,844],[768,1024],[1024,768],[1280,720],[1440,900],[1920,1080],[2560,1440]];
export const paths=['/','/about','/services',...['kundli-matching','kundli-prediction','vastu-consultation','numerology'].map(id=>'/services/'+id),'/contact','/booking','/privacy','/terms','/booking-policy'];
export async function fixture(context,origin,{otp=false,mode='on',blockedAssets=false,responseDelay=0}={}){
 const policy=structuredClone(business),calls=[],blocked=[],assets=[];policy.booking_verification.email=otp;policy.required_contacts=otp?['email','phone']:['phone'];
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){blocked.push(url.origin);return route.abort();}
  if(blockedAssets&&(url.pathname.startsWith('/fonts/')||/\.(woff2|webp|jpeg|svg)$/.test(url.pathname)))return route.abort();
  if(!url.pathname.startsWith('/api/')){assets.push(url.pathname);return route.continue();}
  calls.push({path:url.pathname,method:request.method()});if(responseDelay)await new Promise(resolve=>setTimeout(resolve,responseDelay));
  if(url.pathname==='/api/service-state')return mode==='unknown'?route.fulfill({status:503,json:{code:'synthetic_unknown'}}):route.continue();
  let value,status=200;const now=Date.now(),body=request.postData()?request.postDataJSON():{};
  if(url.pathname==='/api/booking-policy')value={policy,quote_version:'a'.repeat(64),booking_verification_policy_hash:'b'.repeat(64),server_now:new Date(now).toISOString(),schedule_browsing_open:true,receipt_access:{version:1,key_id:'current'}};
  else if(url.pathname==='/api/availability'){
   const service=policy.services.find(s=>s.id===url.searchParams.get('service_id')),date=url.searchParams.get('day'),starts=date+'T06:00:00Z';
   value={date,server_now:new Date(now).toISOString(),service:{...service,amount_paise:service.pricing.amount_paise,questions:1,currency:'INR',timezone:policy.timezone,quote_version:'a'.repeat(64)},slots:Date.parse(starts)>now?[{starts_at:starts,ends_at:new Date(Date.parse(starts)+service.duration_minutes*60000).toISOString()}]:[]};
  }else if(url.pathname==='/api/checkout-context')value={ready:true,renewed:false};
  else if(url.pathname.startsWith('/api/booking-verification/'))value={code:'ok',state:'awaiting_verification',challenge_id:'11111111-1111-4111-8111-111111111111',generation:1,booking_verification_policy_hash:'b'.repeat(64),expires_at:new Date(now+300000).toISOString()};
  else if(url.pathname==='/api/contact/policy')value={version:1,receipt_key_id:'current'};
  else if(/^\/api\/contact\/(start|status|verify|resend)$/.test(url.pathname))value={code:'ok',request_id:body.request_id,state:url.pathname.endsWith('/verify')?'received':'awaiting_verification',generation:1,sends_remaining:2,verification_delivery:'queued',server_now:new Date(now).toISOString(),code_expires_at:new Date(now+300000).toISOString(),resend_after:new Date(now+60000).toISOString()};
  else {status=503;value={code:'synthetic_unavailable'};}
  await route.fulfill({status,json:value,headers:{'cache-control':'no-store'}});
 });
 return {calls,blocked,assets,policy};
}
export async function ready(page,path,origin){
 await page.goto(origin+path,{waitUntil:'networkidle'});
 await page.locator('#page-content h1').waitFor({state:'visible'});
 await page.waitForFunction(()=>{const h=document.querySelector('#page-content h1');return h?.getBoundingClientRect().width>0&&!document.querySelector('main>p[role=status]');});
 await page.evaluate(()=>document.fonts.ready);
}
