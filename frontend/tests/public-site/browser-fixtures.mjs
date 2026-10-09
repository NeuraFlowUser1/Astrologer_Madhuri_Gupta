/** Test-only synthetic contracts. Never proxies an application/provider request. */
import {syntheticResponses} from './synthetic-responses.mjs';
export {business} from './synthetic-responses.mjs';
export const viewports=[[320,740],[390,844],[768,1024],[1024,768],[1280,720],[1440,900],[1920,1080],[2560,1440]];
export const paths=['/','/about','/services',...['kundli-matching','kundli-prediction','vastu-consultation','numerology'].map(id=>'/services/'+id),'/contact','/booking','/privacy','/terms','/booking-policy'];
export async function fixture(context,origin,{otp=false,mode='on',blockedAssets=false,responseDelay=0}={}){
 const {policy,respond}=syntheticResponses({otp,mode}),calls=[],blocked=[],assets=[],blockedAssetsPaths=[];
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(['https://fonts.googleapis.com','https://fonts.gstatic.com'].includes(url.origin)&&request.method()==='GET')return route.continue();
  if(url.origin!==origin){blocked.push(url.origin);return route.abort();}
  if(blockedAssets&&(url.pathname.startsWith('/fonts/')||/\.(woff2|avif|webp|jpe?g|png|svg)$/.test(url.pathname))){blockedAssetsPaths.push(url.pathname);return route.abort();}
  if(!url.pathname.startsWith('/api/')){assets.push(url.pathname);return route.continue();}
  calls.push({path:url.pathname,method:request.method()});if(responseDelay)await new Promise(resolve=>setTimeout(resolve,responseDelay));
  const body=request.postData()?request.postDataJSON():{}, {value,status}=respond(url,request.method(),body);
  await route.fulfill({status,json:value,headers:{'cache-control':'no-store'}});
 });
 return {calls,blocked,assets,blockedAssetsPaths,policy};
}
export async function ready(page,path,origin){
 await page.goto(origin+path,{waitUntil:'networkidle'});
 await page.locator('#page-content h1').waitFor({state:'visible'});
 await page.waitForFunction(()=>{const h=document.querySelector('#page-content h1');return h?.getBoundingClientRect().width>0&&!document.querySelector('main>p[role=status]');});
 await page.evaluate(()=>document.fonts.ready);
}
