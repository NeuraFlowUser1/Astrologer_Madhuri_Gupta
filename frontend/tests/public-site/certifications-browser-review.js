/* Local Chromium review; read-only state fixture, no real provider operations. */
globalThis.certificateBrowserReview=async(page)=>{
 const context=await page.context().browser().newContext({reducedMotion:'reduce'}),p=await context.newPage(),results=[],errors=[];
 const evidence='/mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan/design-review/2026-10-12-about-certifications/evidence/';
 const check=(v,m)=>{if(!v)throw Error(m);};p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/api/service-state',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({enabled:true,activation_epoch:'11111111-1111-4111-8111-111111111111'})}));
 try{
  for(const [width,height] of [[320,800],[390,844],[768,1024],[1440,900],[1920,1080]]){
   await p.setViewportSize({width,height});await p.goto('http://127.0.0.1:4187/about');await p.locator('#certifications').waitFor();
   await p.locator('#certifications img').evaluateAll(imgs=>Promise.all(imgs.map(i=>{i.loading='eager';return i.decode();})));
   check(await p.locator('.certificate-item').count()===4,'Missing certificate');
   check(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'About overflow '+width);
   const geometry=await p.evaluate(()=>({galleryHeight:document.querySelector('#certifications').getBoundingClientRect().height,backdrops:[...document.querySelectorAll('.welcome-sheet,.invite-layer')].map(e=>({class:e.className,height:e.getBoundingClientRect().height,top:e.getBoundingClientRect().top+scrollY})),scenes:[...document.querySelectorAll('.sarsa-about>section[id]')].map(e=>({id:e.id,height:e.getBoundingClientRect().height}))}));
   await p.locator('#certifications').screenshot({path:evidence+'about-certificates-'+width+'.png'});
   const opener=p.getByRole('button',{name:'View Jyotish Shastri certificate',exact:true});await opener.click();
   const dialog=p.getByRole('dialog');await dialog.waitFor();await p.locator('.certificate-image-canvas img').evaluate(i=>i.decode());
   const bounds=await dialog.boundingBox();check(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=width+1&&bounds.y+bounds.height<=height+1,'Reader overflow '+width);
   check(await p.getByRole('button',{name:'Previous certificate',exact:true}).isDisabled(),'First boundary');
   for(let i=0;i<8;i++){await p.keyboard.press('Tab');check(await dialog.evaluate(e=>e.contains(document.activeElement)),'Focus left dialog');}
   await p.getByRole('button',{name:'Zoom in',exact:true}).click();check(await p.locator('.certificate-image-canvas').getAttribute('data-zoomed')==='true','Zoom');
   await p.getByRole('button',{name:'Fit to screen',exact:true}).click();
   for(let i=0;i<3;i++)await p.getByRole('button',{name:'Next certificate',exact:true}).click();
   check(await p.getByRole('button',{name:'Next certificate',exact:true}).isDisabled(),'Last boundary');
   await p.locator('.certificate-image-canvas img').evaluate(i=>i.decode());await p.screenshot({path:evidence+'certificate-dialog-'+width+'.png'});
   await p.keyboard.press('Escape');await dialog.waitFor({state:'detached'});check(await opener.evaluate(e=>document.activeElement===e),'Return focus');
   await opener.click();await p.mouse.click(2,2);await dialog.waitFor({state:'detached'});
   await p.getByRole('navigation',{name:'Main navigation',exact:true}).getByRole('link',{name:'Reviews',exact:true}).click();await p.locator('.reviews-waiting-photo').waitFor();
   check(await p.locator('.opening-intro[role=status]').innerText()==='Reviews will be added here.','Honest waiting state');
   check(await p.locator('blockquote').count()===0,'Unexpected public endorsement');
   check(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Reviews overflow '+width);
   check(await p.getByRole('navigation',{name:'Footer navigation',exact:true}).getByRole('link',{name:'Reviews',exact:true}).count()===1,'Footer Reviews missing');
   check(await p.getByRole('navigation',{name:'Main navigation',exact:true}).getByRole('link',{name:'Reviews',exact:true}).getAttribute('aria-current')==='page','Selected review');
   await p.locator('.reviews-waiting-photo img').evaluate(i=>i.decode());await p.screenshot({path:evidence+'reviews-'+width+'.png',fullPage:true});results.push({width,height,certificates:4,overflow:false,readerControls:'passed',reviewNavigation:'passed',geometry});
  }
  await p.setViewportSize({width:1440,height:900});await p.route('**/media/certificates/jyotish-shastri-full.webp',r=>r.fulfill({status:404,body:'Synthetic missing image'}));
  await p.goto('http://127.0.0.1:4187/about');await p.getByRole('button',{name:'View Jyotish Shastri certificate',exact:true}).click();await p.locator('.certificate-image-error').waitFor();check(await p.locator('.certificate-image-error a').getAttribute('href')==='/media/certificates/jyotish-shastri-original.jpeg','Image failure lost original');
  await p.getByRole('button',{name:'Next certificate',exact:true}).click();await p.locator('.certificate-image-canvas img').evaluate(i=>i.decode());check(await p.locator('.certificate-image-error').count()===0,'Failure not reset');
  await p.evaluate(()=>{history.pushState({},'','/services');dispatchEvent(new PopStateEvent('popstate'));});await p.locator('.sarsa-services').waitFor();check(await p.getByRole('dialog').count()===0,'Route unmount left dialog');check(await p.evaluate(()=>getComputedStyle(document.documentElement).overflow!=='hidden'),'Route unmount kept scroll lock');
  check(errors.length===0,'Page errors: '+errors.join(','));return {result:'passed',viewports:results,errorFallback:'passed',routeCleanup:'passed',pageErrors:errors};
 }finally{await context.close();}
}
