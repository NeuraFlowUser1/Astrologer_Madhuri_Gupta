/* Hosted read-only assessment, invoked by the Playwright browser tool.
 * Fresh contexts use real responses. No customer operation or credential is used.
 * The controlling about:blank fragment selects one bounded phase; see docs.
 */
async (page) => {
  const origin='https://www.sarsajyotishsansthan.com';
  const paths=['/','/about','/services','/services/kundli-prediction','/services/kundli-matching','/services/vastu-consultation','/services/numerology','/contact','/privacy','/terms','/booking','/booking-policy','/booking/receipt'];
  const services=['kundli-matching','kundli-prediction','vastu-consultation','numerology'];
  const phase=new URL(page.url()).hash.slice(1);
  if(!['routes-390','routes-1440','edges','interfaces','services','api','booking-layouts'].includes(phase))throw Error('Select a documented phase on the controlling about:blank tab.');
  const report={kind:'actual-hosted-read-only',origin,phase,started:new Date().toISOString(),cases:[],blockedWrites:[],externalFailures:[],warnings:[],internalLinks:[],assets:[]};
  const browser=page.context().browser();
  let assertions=0;
  function check(condition,message){assertions++;if(!condition)throw Error(message);}
  const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
  context.setDefaultTimeout(15000);
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin===origin && !['GET','HEAD'].includes(request.method())){
      report.blockedWrites.push({path:url.pathname,method:request.method()});
      return route.abort('blockedbyclient');
    }
    return route.continue();
  });
  const current=await context.newPage();
  let pageErrors=[],firstPartyFailures=[];
  current.on('pageerror',error=>pageErrors.push(error.message));
  current.on('console',message=>{if(message.type()==='warning')report.warnings.push(message.text().slice(0,240));});
  current.on('response',response=>{
    const url=new URL(response.url());
    if(url.origin===origin && response.status()>=400)firstPartyFailures.push({path:url.pathname,status:response.status()});
    if(url.origin!==origin && response.status()>=400)report.externalFailures.push({origin:url.origin,status:response.status()});
  });
  async function run(label,work){
    const start=Date.now(),before=assertions;
    pageErrors=[];firstPartyFailures=[];
    try{const detail=await work();check(pageErrors.length===0,'Page errors: '+pageErrors.join('; '));check(firstPartyFailures.length===0,'First-party errors: '+JSON.stringify(firstPartyFailures));report.cases.push({label,status:'passed',assertions:assertions-before,elapsed_ms:Date.now()-start,...detail});}
    catch(error){report.cases.push({label,status:'failed',assertions:assertions-before,elapsed_ms:Date.now()-start,error:error.message,pageErrors,firstPartyFailures});}
  }
  async function visit(path,width=1440,height=900){
    await current.setViewportSize({width,height});
    const response=await current.goto(origin+path,{waitUntil:'domcontentloaded',timeout:45000});
    check(response?.status()===200,'Page HTTP status '+response?.status());
    await current.locator('#page-content h1').waitFor({state:'visible',timeout:30000});
    if(path==='/booking'){
      await current.locator('input[name=service]').last().waitFor({state:'attached',timeout:30000});
      check(await current.locator('input[name=service]').count()===4,'Live service choices have not finished loading');
    }
    await current.evaluate(()=>document.fonts.ready);
    await current.waitForTimeout(250);
  }
  async function layout(path,width,height){
    await visit(path,width,height);
    // Visit the actual lazy media rather than treating offscreen placeholders as proof.
    await current.evaluate(async()=>{
      const distance=Math.max(400,innerHeight*.8);
      for(let y=0;y<document.documentElement.scrollHeight;y+=distance){scrollTo(0,y);await new Promise(resolve=>setTimeout(resolve,45));}
      scrollTo(0,0);
    });
    await current.waitForTimeout(600);
    const detail=await current.evaluate(()=>({
      path:location.pathname,title:document.title,canonical:document.querySelector('link[rel=canonical]')?.href,
      description:document.querySelector('meta[name=description]')?.content,
      robots:document.querySelector('meta[name=robots]')?.content,
      h1:document.querySelectorAll('#page-content h1').length,
      headers:document.querySelectorAll('.sarsa-header').length,footers:document.querySelectorAll('.sarsa-footer').length,
      overflow:document.documentElement.scrollWidth-innerWidth,
      images:[...document.querySelectorAll('main img')].map(node=>({src:node.currentSrc||node.src,loaded:node.complete&&node.naturalWidth>0,altPresent:node.hasAttribute('alt')})),
      links:[...document.querySelectorAll('a[href]')].map(node=>node.href),
      active:[...document.querySelectorAll('header nav a[aria-current=page]')].map(node=>({href:node.getAttribute('href'),weight:parseInt(getComputedStyle(node.querySelector('.sarsa-nav-label')||node).fontWeight,10)})),
      api:performance.getEntriesByType('resource').filter(entry=>entry.name.includes('/api/')).map(entry=>new URL(entry.name).pathname),
      entryScripts:[...document.querySelectorAll('script[src]')].map(node=>node.src)
    }));
    check(detail.path===path,'Unexpected destination '+detail.path);
    check(detail.h1===1,'Expected one main title');
    check(detail.headers===1&&detail.footers===1,'Expected one shared header and footer');
    check(detail.overflow<=1,'Sideways overflow '+detail.overflow+'px');
    check(detail.title.includes('Sarsa')&&!detail.title.includes('Page not found'),'Missing route title');
    check(detail.canonical===origin+path,'Incorrect canonical '+detail.canonical);
    check(!!detail.description,'Missing description');
    check(detail.images.every(image=>image.loaded&&image.altPresent),'Broken image or missing alt attribute: '+JSON.stringify(detail.images.filter(image=>!image.loaded||!image.altPresent)));
    if(path==='/booking/receipt')check(detail.robots.includes('noindex'),'Private lookup must be noindex');
    if(path==='/about'||path.startsWith('/services')||path==='/contact'){
      const target=path.startsWith('/services')?'/services':path;
      check(detail.active.some(link=>link.href===target&&link.weight>=600),'Selected navigation does not stand out');
    }
    report.internalLinks.push(...detail.links.filter(link=>link.startsWith(origin)));
    report.assets.push(...detail.entryScripts,...detail.images.map(image=>image.src));
    delete detail.links;
    return {width,height,...detail};
  }
  try{
    if(phase==='routes-390'||phase==='routes-1440'){
      const width=phase==='routes-390'?390:1440,height=width===390?844:900;
      for(const path of paths)await run('route '+path+' '+width,()=>layout(path,width,height));
    }
    if(phase==='edges')for(const [width,height] of [[320,740],[768,1024],[1920,1080]])for(const path of ['/','/services','/contact','/booking'])await run('edge '+path+' '+width,()=>layout(path,width,height));
    if(phase==='booking-layouts'){
      for(const [width,height] of [[390,844],[1440,900],[320,740],[768,1024],[1920,1080]])await run((width===390||width===1440?'route':'edge')+' /booking '+width,()=>layout('/booking',width,height));
      await run('Booking through review without submitting',async()=>{
        await visit('/booking');
        const response=await context.request.get(origin+'/api/booking-policy',{timeout:45000});check(response.status()===200,'Policy unavailable');const policy=await response.json();
        const tomorrow=new Date(Date.parse(policy.server_now)+86400000),dateLabel=new Intl.DateTimeFormat('en-GB',{timeZone:policy.policy.timezone,weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(tomorrow);
        await current.locator('.service-card').filter({hasText:'Kundli Matching'}).click();
        await current.locator('.abs-date-group button[aria-haspopup="dialog"]').click();
        await current.getByRole('button',{name:new RegExp(dateLabel)}).click();
        await current.locator('.slot-option').first().waitFor({state:'visible',timeout:20000});
        await current.locator('.slot-option').first().click();
        await current.getByRole('button',{name:'Fill your details →',exact:true}).click();
        await current.locator('#full_name').fill('Read-only Browser Check');await current.locator('#phone').fill('0000000000');
        await current.getByRole('button',{name:'Review your booking →',exact:true}).click();
        const summary=await current.locator('.summary-sheet').innerText();
        check(summary.includes('Kundli Matching'),'Selected service missing from review');check(summary.includes('Read-only Browser Check'),'Draft name missing from review');
        check(await current.locator('.submit-button').isDisabled(),'Payment must stay disabled without acknowledgement');
        check(report.blockedWrites.length===0,'A write was attempted before submitting');
        return {day:dateLabel,selectedSlot:true,reachedReview:true,customerDetailsSubmitted:false,bookingCreated:false};
      });
    }
    if(phase==='interfaces'){
      await run('Home FAQs and back to top',async()=>{
        await visit('/');const items=current.locator('.faq-list details');check(await items.count()===8,'Expected eight Home FAQs');
        await items.nth(0).locator('summary').click();check(await items.nth(0).getAttribute('open')!==null,'FAQ did not open');
        await items.nth(1).locator('summary').click();check(await current.locator('.faq-list details[open]').count()===1,'FAQ opening did not collapse the previous answer');
        await current.locator('footer').scrollIntoViewIfNeeded();await current.getByRole('button',{name:'Back to top',exact:true}).click();
        await current.waitForFunction(()=>scrollY<5);check(await current.evaluate(()=>scrollY<5),'Back to top did not reach the beginning');
      });
      await run('Home combined chapter and staged motion',async()=>{
        await current.emulateMedia({reducedMotion:'no-preference'});await visit('/');
        await current.waitForFunction(()=>document.querySelector('#welcome')?.dataset.motionProgress==='1.000',{},{timeout:10000});
        const section=current.locator('#conversation');await section.scrollIntoViewIfNeeded();
        await current.waitForFunction(()=>document.querySelector('#conversation')?.dataset.motionProgress==='1.000',{},{timeout:12000});
        check(await section.locator('[data-process-stage]').count()===1,'Process is not inside the combined chapter');check(await section.locator('.steps article').count()===3,'Missing three steps');
        const steps=section.locator('.steps article'),circle=steps.first().locator('.step-number');
        const before=await circle.evaluate(node=>({shadow:getComputedStyle(node).boxShadow,weight:getComputedStyle(node).fontWeight}));
        await steps.first().hover();await current.waitForTimeout(400);
        const after=await circle.evaluate(node=>({shadow:getComputedStyle(node).boxShadow,weight:getComputedStyle(node).fontWeight}));
        check(before.shadow!==after.shadow||before.weight!==after.weight,'Step circle has no hover change');
        await current.emulateMedia({reducedMotion:'reduce'});return {heroSettled:true,combinedChapterSettled:true,steps:3};
      });
      await run('About approach, hover and service actions',async()=>{
        await current.emulateMedia({reducedMotion:'no-preference'});await visit('/about');await current.locator('a[href="#approach"]').first().click();
        await current.waitForFunction(()=>location.hash==='#approach');check(await current.locator('#approach-scene article').count()===3,'Missing approach cards');
        await current.waitForFunction(()=>document.querySelector('#approach')?.dataset.motionProgress==='1.000',{},{timeout:12000});
        await current.mouse.move(0,0);
        const card=current.locator('#approach-scene article').first();const before=await card.evaluate(node=>getComputedStyle(node).translate);
        await card.hover();await current.waitForTimeout(400);const after=await card.evaluate(node=>getComputedStyle(node).translate);
        check(before!==after,'Approach card does not react to hover');
        const rows=current.locator('.service-row');check(await rows.count()===4,'Missing service rows');
        for(let i=0;i<4;i++){check(await rows.nth(i).locator('.row-actions a').count()===2,'Explore/Book pair missing');}
        const action=current.locator('.approach-action');check(await action.evaluate(node=>parseInt(getComputedStyle(node).fontWeight,10))>=600,'Services action is not emphasized');
        await current.emulateMedia({reducedMotion:'reduce'});
      });
      await run('Contact links, enquiry fields and Google Maps',async()=>{
        await visit('/contact');check(await current.locator('main a[href="/booking/receipt"]').count()>=1,'Missing booking access link');
        check(await current.locator('#visitor-name').getAttribute('required')!==null,'Contact name is not required');
        check(await current.locator('#visitor-email').getAttribute('required')!==null,'Contact email is not required');
        const map=current.locator('iframe[title*="Google Maps"]');check(await map.count()===1,'Missing Google Maps frame');
        check((await map.getAttribute('src')).startsWith('https://www.google.com/maps/embed'),'Wrong map source');
        check((await current.locator('.contact-location address').innerText()).includes('8, Gailana Road, LIC Colony, Agra - 282007'),'Incorrect address');
        await current.locator('.contact-location').scrollIntoViewIfNeeded();await map.waitFor({state:'visible'});
        return {mapFramePresent:true,thirdPartyMapAcceptance:'not claimed; visible embed inspected separately'};
      });
      await run('Booking choices, date picker and optional email',async()=>{
        await visit('/booking');await current.locator('input[name=service]').last().waitFor({state:'attached',timeout:30000});
        check(await current.locator('input[name=service]').count()===4,'Missing live service choices');
        check(await current.locator('#full_name').getAttribute('required')!==null,'Name is not required');
        check(await current.locator('#phone').getAttribute('required')!==null,'Phone is not required');
        check(await current.locator('#email').getAttribute('required')===null,'Email unexpectedly required with verification OFF');
        check(await current.locator('main a[href="/booking/receipt"]').count()>=1,'Missing booking-details link');
        await current.locator('.service-card').filter({hasText:'Kundli Matching'}).click();
        // React Aria combines labelled-by text with the calendar button's label.
        // Target the actual popup button, then prove that its named dialog opens.
        await current.locator('.abs-date-group button[aria-haspopup="dialog"]').click();
        const picker=current.getByRole('dialog',{name:'Appointment date',exact:true});await picker.waitFor({state:'visible'});
        check(await picker.isVisible(),'Date picker did not open');await current.keyboard.press('Escape');check(!await picker.isVisible(),'Date picker did not close');
        await current.locator('#full_name').fill('Read-only Browser Check');await current.locator('#phone').fill('0000000000');
        const other=await context.newPage();await other.goto('about:blank');await current.bringToFront();await other.close();
        check(await current.locator('#full_name').inputValue()==='Read-only Browser Check','Draft name lost on tab return');
        check(await current.locator('#phone').inputValue()==='0000000000','Draft phone lost on tab return');
        check(await current.locator('.submit-button').isDisabled(),'Payment button active without a complete appointment');
        return {serviceCount:4,createdBooking:false,submittedDetails:false};
      });
      await run('Name-and-phone access and old entry',async()=>{
        await visit('/booking/receipt');const form=current.locator('.abs-lookup-form');check(await form.count()===1,'Missing lookup form');
        check(await form.locator('input[name=full_name][required]').count()===1,'Missing required full name');
        check(await form.locator('input[name=phone][required]').count()===1,'Missing required phone');
        check(await form.locator('input').count()===2,'Unexpected reference/code field');check(!(await form.evaluate(node=>node.checkValidity())),'Empty lookup form accepted');
        await current.goto(origin+'/booking-help',{waitUntil:'domcontentloaded',timeout:45000});await current.waitForURL(origin+'/booking/receipt');
        check(new URL(current.url()).pathname==='/booking/receipt','Old booking-help link did not reach new access page');return {lookupSubmitted:false};
      });
      await run('Client navigation and selected link',async()=>{
        await visit('/');await current.locator('header nav a[href="/services"]').click();await current.waitForURL(origin+'/services');
        await current.locator('.service-directory').waitFor();check(await current.locator('header').count()===1,'Duplicate header after navigation');
        check(await current.locator('header nav a[href="/services"]').getAttribute('aria-current')==='page','Services link is not selected');
        await current.goBack();await current.locator('.sarsa-home').waitFor();check(new URL(current.url()).pathname==='/','Browser Back failed');
      });
    }
    if(phase==='services'){
      await run('Service directory imagery, buttons and divider',async()=>{
        await visit('/services');const cards=current.locator('[data-directory-card]');check(await cards.count()===4,'Expected four service cards');
        for(let i=0;i<4;i++){const card=cards.nth(i);await card.scrollIntoViewIfNeeded();check(await card.locator('.directory-photo img').count()===1,'Service photograph missing');check(await card.locator('.service-actions a').count()===2,'Explore/Book actions missing');
          const values=await card.locator('.service-actions').evaluate(node=>({alignment:getComputedStyle(node).justifyContent,weights:[...node.querySelectorAll('a')].map(a=>parseInt(getComputedStyle(a).fontWeight,10))}));
          check(values.alignment==='flex-end','Service buttons not right aligned');check(values.weights.every(weight=>weight>=600),'Service actions not emphasized');}
        const gap=await current.locator('.first-service-guide').evaluate(node=>({top:node.getBoundingClientRect().top,directoryBottom:document.querySelector('.service-directory').getBoundingClientRect().bottom}));check(gap.top-gap.directoryBottom>=40,'Divider touches service cards');
      });
      for(const service of services)await run('Service illustrations '+service,async()=>{
        await visit('/services/'+service);const story=current.locator('.service-visual-story');await story.scrollIntoViewIfNeeded();
        const choices=story.locator('.story-choices button');check(await choices.count()===3,'Expected three explanation choices');
        for(let i=0;i<3;i++){await choices.nth(i).click();check(await choices.nth(i).getAttribute('aria-pressed')==='true','Topic selection not updated');check(await story.locator('.story-choices button[aria-pressed=true]').count()===1,'Multiple selected topics');}
        const first=await story.locator('.story-picture img').last().getAttribute('src');await story.getByRole('button',{name:'Next →',exact:true}).click();
        await story.locator('.story-controls').getByText('2 of 2',{exact:true}).waitFor({state:'visible',timeout:20000});
        const second=await story.locator('.story-picture img').last().getAttribute('src');check(first!==second,'Picture did not change');
        check(await story.locator('.story-picture img').last().evaluate(node=>node.complete&&node.naturalWidth>0),'Second picture failed to load');
        await story.getByRole('button',{name:'← Previous',exact:true}).click();await story.locator('.story-controls').getByText('1 of 2',{exact:true}).waitFor({state:'visible'});
        check(await story.locator('.story-picture img').last().getAttribute('src')===first,'Previous picture not restored');return {service,topics:3,pictures:2};
      });
    }
    if(phase==='api'){
      let policy;
      for(const [path,expected] of [['/api/health',200],['/api/service-state',200],['/api/booking-policy',200],['/api/contact/policy',200],['/api/studio/status',401],['/api/enquiry-studio/status',401],['/api/company/support/status',401]])await run('HTTP '+path,async()=>{
        const response=await context.request.get(origin+path,{maxRedirects:0,timeout:45000}),type=response.headers()['content-type']||'';
        check(response.status()===expected,'Unexpected HTTP status '+response.status());check(type.includes('application/json'),'Expected JSON response');
        check((response.headers()['cache-control']||'').includes('no-store'),'Response permits storage');
        const data=await response.json();if(path==='/api/health')check(data.status==='online','Application is offline');
        if(path==='/api/service-state')check(data.enabled===true,'Booking is not ON');
        if(path==='/api/booking-policy'){policy=data;check(data.policy.services.length===4,'Policy missing services');check(data.policy.required_contacts.includes('phone'),'Phone not required');check(data.policy.booking_verification.email===false,'Email verification differs from saved OFF choice');}
        return {path,http:response.status(),noStore:true};
      });
      if(policy){const tomorrow=new Date(Date.parse(policy.server_now)+86400000);const day=new Intl.DateTimeFormat('en-CA',{timeZone:policy.policy.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(tomorrow);
        for(const service of services)await run('Availability '+service,async()=>{const response=await context.request.get(origin+'/api/availability?'+new URLSearchParams({service_id:service,day,questions:'1'}),{timeout:45000});check(response.status()===200,'Availability HTTP '+response.status());const data=await response.json();check(Array.isArray(data.slots),'Availability has no slots array');return {service,day,availableSlots:data.slots.length};});}
      await run('Public sitemap and robots',async()=>{
        const response=await context.request.get(origin+'/sitemap.xml');check(response.status()===200,'Sitemap unavailable');const xml=await response.text(),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match=>match[1]);
        const expected=paths.filter(path=>path!=='/booking/receipt');check(urls.length===expected.length,'Unexpected sitemap route count '+urls.length);check(expected.every(path=>urls.includes(origin+path)),'Public route absent from sitemap');
        check(!urls.some(url=>url.includes('/booking/receipt')||url.includes('/studio')||url.includes('/company')),'Private path indexed');
        const robots=await context.request.get(origin+'/robots.txt');check(robots.status()===200,'Robots unavailable');check((await robots.text()).includes('Sitemap: '+origin+'/sitemap.xml'),'Robots missing sitemap');return {publicRoutes:urls.length};
      });
      await run('Unpublished Testimonials redirect',async()=>{const response=await context.request.get(origin+'/testimonials',{maxRedirects:0});check([301,308].includes(response.status()),'Unexpected unpublished route behavior');check(response.headers().location==='/about','Unexpected redirect target');return {http:response.status(),location:'/about',newPageHostedAcceptance:false};});
      for(const path of ['/studio','/studio/calendar','/enquiries-studio','/company/booking-control','/company/booking-support','/company/google-repair'])await run('Private sign-in '+path,async()=>{const response=await context.request.get(origin+path,{maxRedirects:0,timeout:45000});check(response.status()===200,'Sign-in page HTTP '+response.status());check((response.headers()['x-robots-tag']||'').includes('noindex'),'Private entry permits indexing');const body=await response.text();check(/sign.in|log.in|password|continue with google/i.test(body),'Missing sign-in boundary');return {path,http:200,signedIn:false};});
      await run('Unknown page',async()=>{const response=await context.request.get(origin+'/sarsa-hosted-check-page-does-not-exist',{maxRedirects:0});check(response.status()===404,'Unknown page does not return 404');return {http:404};});
    }
  } finally {
    await context.close();report.finished=new Date().toISOString();report.assertions=assertions;report.internalLinks=[...new Set(report.internalLinks)];report.assets=[...new Set(report.assets)];report.warnings=[...new Set(report.warnings)];report.externalFailures=[...new Map(report.externalFailures.map(item=>[JSON.stringify(item),item])).values()];
  }
  report.passed=report.cases.filter(item=>item.status==='passed').length;report.failed=report.cases.filter(item=>item.status==='failed').length;
  return report;
}
