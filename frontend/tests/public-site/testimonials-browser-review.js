/* Focused public-page browser checks, passed as a function to the browser tool.
 * Uses the actual public route and approved content. Local display-state reads are intercepted.
 * Requires the local Vite server on port 4187. Not a production entry.
 */
globalThis.approvedReviewsBrowserReview=async (page) => {
  const browser=page.context().browser(),origin='http://127.0.0.1:4187';
  const evidence='/mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan/design-review/2026-10-12-approved-reviews-publication/evidence/';
  const report={kind:'approved-reviews-public-route',widths:[],interactions:[],contexts:[],failures:[],started:new Date().toISOString()};
  function check(condition,message){if(!condition)throw Error(message);}
  async function review(label,options,work){
    const context=await browser.newContext(options),errors=[],blocked=[];
    await context.route('**/*',route=>{
      const url=new URL(route.request().url());
      // The actual application shell already loads these public font resources.
      if(['https://fonts.googleapis.com','https://fonts.gstatic.com'].includes(url.origin)&&route.request().method()==='GET')return route.continue();
      if(url.origin!==origin){blocked.push(url.origin);return route.abort();}
      if(url.pathname==='/api/service-state')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({enabled:options.bookingOff!==true,activation_epoch:'12345678-1234-4321-8123-123456789abc'})});
      if(url.pathname.startsWith('/api/')){blocked.push(url.pathname);return route.abort();}
      return route.continue();
    });
    if(options.inline)await context.addInitScript(()=>{HTMLDialogElement.prototype.showModal=undefined;});
    const current=await context.newPage();current.on('pageerror',error=>errors.push(error.message));
    try{
      await current.goto(origin+'/testimonials');await current.locator('.story-card').first().waitFor();
      await work(current);check(errors.length===0,'Browser errors: '+errors.join(', '));check(blocked.length===0,'Unexpected requests: '+blocked.join(', '));
      report.contexts.push({label,status:'passed',pageErrors:errors.length,unexpectedRequests:blocked.length});
    }catch(error){report.failures.push({label,message:error.message});await current.screenshot({path:evidence+'integration-failure-'+label+'.png',fullPage:true});}
    finally{await context.close();}
  }
  await review('responsive',{viewport:{width:1440,height:900}},async current=>{
    for(const [width,height] of [[320,800],[390,844],[768,1024],[1050,800],[1051,800],[1440,900],[1920,1080]]){
      await current.setViewportSize({width,height});await current.waitForTimeout(350);
      const metrics=await current.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,links:[...document.querySelectorAll('.sarsa-header nav a')].map(link=>({height:link.getBoundingClientRect().height,right:link.getBoundingClientRect().right})),cards:document.querySelectorAll('.story-card').length}));
      check(metrics.document===width,'Sideways overflow at '+width);check(metrics.links.length===4,'Shared navigation missing a link');check(metrics.links.every(link=>link.height>=44&&link.right<=width),'Navigation target outside the screen');check(metrics.cards===6,'Initial collection count changed');report.widths.push({width,height,overflow:0,headerTargets:4,status:'passed'});
    }
  });
  for(const width of [1440,390])await review('reading-'+width,{viewport:{width,height:width===390?844:900}},async current=>{
    await current.waitForTimeout(1500);
    await current.locator('.read-stories').focus();await current.keyboard.press('Enter');await current.waitForTimeout(500);
    check(await current.evaluate(()=>location.hash==='#stories'&&document.activeElement.dataset.scrollDestination==='stories'),'Keyboard collection handoff failed');
    const collection=current.locator('.story-card');await current.locator('#more-stories').focus();await current.keyboard.press('Enter');
    check(await collection.count()===12,'See more did not reveal twelve');check(await current.evaluate(()=>document.activeElement.dataset.story===document.querySelectorAll('.story-card')[6].dataset.story),'See more lost reading focus');check(await current.locator('#more-stories').count()===0,'Completed See more remained active');
    for(const category of ['kundli-prediction','kundli-matching','vastu-consultation','numerology']){
      const control=current.locator('[data-filter="'+category+'"]');await control.click();check(await collection.count()===3,'Wrong service filter count');check(await control.getAttribute('aria-pressed')==='true','Selected service was not announced');check(await current.locator('[data-filter][aria-pressed=true]').count()===1,'Multiple filters selected');
    }
    await current.locator('[data-filter=all]').click();check(await collection.count()===6,'All did not reset collection');
    for(const scene of ['featured','echoes']){
      await current.locator('.'+scene).scrollIntoViewIfNeeded();await current.waitForTimeout(1100);
      const measure=()=>current.locator('.'+scene).evaluate(el=>el.getBoundingClientRect().height);
      const before=await measure();
      if(scene==='featured')for(let i=0;i<3;i++){await current.locator('#feature-next').click();await current.waitForTimeout(230);check(Math.abs((await measure())-before)<1,'Featured story moved chapter height');}
      else for(const theme of ['simple','calm','heard']){await current.locator('[data-theme='+theme+']').click();await current.waitForTimeout(210);check(Math.abs((await measure())-before)<1,'Theme change moved chapter height');}
    }
    const opener=current.locator('.story-card button').first(),handle=await opener.elementHandle();await opener.click();
    check(await current.locator('dialog[open]').count()===1,'Native reader failed to open');check(await current.evaluate(()=>document.activeElement.id==='dialog-title'&&document.body.style.overflow==='hidden'),'Reader title focus/scroll lock failed');
    for(const key of ['Tab','Tab','Shift+Tab']){await current.keyboard.press(key);check(await current.evaluate(()=>document.activeElement.id==='dialog-close'),'Native reader let keyboard focus escape');}
    await current.locator('dialog').evaluate(el=>{el.scrollTop=el.scrollHeight;});check(await current.locator('#dialog-close').isVisible(),'Close disappeared while reading');
    await current.screenshot({path:evidence+'integration-reader-'+width+'.png'});
    await current.keyboard.press('Escape');check(await current.locator('dialog').count()===0,'Escape left reader open');check(await current.evaluate(el=>document.activeElement===el,handle),'Escape lost opening action');check(await current.evaluate(()=>document.body.style.overflow===''),'Escape left scrolling locked');
    await opener.click();await current.locator('#dialog-close').click();check(await current.evaluate(el=>document.activeElement===el,handle),'Close lost opening action');
    await opener.click();await current.evaluate(()=>{history.pushState({},'','/services');dispatchEvent(new PopStateEvent('popstate'));});await current.locator('.sarsa-services').waitFor();check(await current.locator('dialog').count()===0,'Route exit retained reader');check(await current.evaluate(()=>document.body.style.overflow===''),'Route exit left scrolling locked');
    report.interactions.push({width,filterGroups:4,revealedStories:12,featuredHeightStable:true,themeHeightStable:true,reader:'keyboard/Close/Escape/unmount passed'});
  });
  await review('inline-reader',{viewport:{width:390,height:844},inline:true},async current=>{
    await current.locator('.story-card button').first().click();check(await current.locator('dialog[data-inline][role=region]').count()===1,'Inline reader missing');check(await current.evaluate(()=>document.body.style.overflow===''),'Inline reader locked scrolling');
    await current.locator('[data-filter=numerology]').click();check(await current.locator('dialog').count()===0,'Filter retained an inline reader');await current.locator('.story-card button').first().click();await current.keyboard.press('Escape');check(await current.locator('dialog').count()===0,'Inline Escape failed');
  });
  await review('reduced-motion',{viewport:{width:390,height:844},reducedMotion:'reduce'},async current=>{
    await current.waitForTimeout(1500);check(await current.evaluate(()=>document.getAnimations().filter(animation=>animation.playState==='running').length===0),'Reduced motion still animated');check(await current.locator('.story-card').count()===6,'Reduced motion hid content');await current.screenshot({path:evidence+'integration-reduced-390.png'});
  });
  await review('booking-off',{viewport:{width:390,height:844},bookingOff:true},async current=>{
    check(await current.locator('a[href="/booking"]').count()===0,'OFF exposed a booking action');check(await current.locator('.invitation a[href="/services"]').count()===1,'OFF removed service exploration');check(await current.locator('.sarsa-header nav a[href="/testimonials"]').getAttribute('aria-current')==='page','Testimonials selection missing');
  });
  report.finished=new Date().toISOString();return report;
}
