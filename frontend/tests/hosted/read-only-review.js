/* Hosted read-only assessment, invoked by the Playwright browser tool.
 * Fresh contexts use real responses. No customer operation or credential is used.
 * The controlling about:blank fragment selects one bounded phase; see docs.
 */
globalThis.hostedReadOnlyReview=async (page) => {
  const origin='https://www.sarsajyotishsansthan.com';
  const paths=['/','/about','/services','/testimonials','/services/kundli-prediction','/services/kundli-matching','/services/vastu-consultation','/services/numerology','/services/prashna-kundali','/contact','/privacy','/terms','/booking','/booking-policy','/booking/receipt'];
  const services=['kundli-matching','kundli-prediction','vastu-consultation','numerology','prashna-kundali'];
  const illustratedServices=services.filter(id=>id!=='prashna-kundali');
  const fixedFees={'kundli-matching':210000,'kundli-prediction':250000,'vastu-consultation':450000,numerology:210000};
  const fragment=new URL(page.url()).hash.slice(1),[phase]=fragment.split('?');
  if(!['routes-390','routes-1440','edges','interfaces','services','api','booking-layouts','prashna','links'].includes(phase))throw Error('Select a documented phase on the controlling about:blank tab.');
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
    try{const detail=await work();check(report.blockedWrites.length===0,'An unsafe request was attempted and blocked');check(pageErrors.length===0,'Page errors: '+pageErrors.join('; '));check(firstPartyFailures.length===0,'First-party errors: '+JSON.stringify(firstPartyFailures));report.cases.push({label,status:'passed',assertions:assertions-before,elapsed_ms:Date.now()-start,...detail});}
    catch(error){report.cases.push({label,status:'failed',assertions:assertions-before,elapsed_ms:Date.now()-start,error:error.message,pageErrors,firstPartyFailures});}
  }
  async function visit(path,width=1440,height=900){
    await current.setViewportSize({width,height});
    const response=await current.goto(origin+path,{waitUntil:'domcontentloaded',timeout:45000});
    check(response?.status()===200,'Page HTTP status '+response?.status());
    await current.locator('#page-content h1').waitFor({state:'visible',timeout:30000});
    if(new URL(path,origin).pathname==='/booking'){
      await current.locator('input[name=service]').last().waitFor({state:'attached',timeout:30000});
      check(await current.locator('input[name=service]').count()===services.length,'Live service choices have not finished loading');
    }
    if(new URL(path,origin).pathname==='/booking/receipt'){
      // Admission starts unavailable until the actual ON state arrives. A generic
      // heading can belong to that initial boundary, rather than the lookup page.
      await current.locator('.abs-lookup-form').waitFor({state:'visible',timeout:30000});
    }
    await current.evaluate(()=>document.fonts.ready);
    await current.waitForTimeout(250);
  }
  async function availableDay(policy,service,questions){
    // Choose from real availability; tomorrow can correctly be a closed Sunday.
    const timezone=policy.policy.timezone,days=Math.min(policy.policy.horizon_days,10),checked=[];
    for(let offset=1;offset<=days;offset++){
      const date=new Date(Date.parse(policy.server_now)+offset*86400000);
      const day=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
      const response=await context.request.get(origin+'/api/availability?'+new URLSearchParams({service_id:service,day,questions:String(questions)}),{timeout:45000});
      check(response.status()===200,'Availability lookup HTTP '+response.status());
      const data=await response.json();check(Array.isArray(data.slots),'Missing available-slot list');checked.push({day,slots:data.slots.length});
      if(data.slots.length)return {day,dateLabel:new Intl.DateTimeFormat('en-GB',{timeZone:timezone,weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(date),data,checked};
    }
    throw Error('No available appointment within the inspected saved horizon: '+JSON.stringify(checked));
  }
  async function chooseDate(dateLabel){
    await current.locator('.abs-date-group button[aria-haspopup="dialog"]').click();
    await current.getByRole('button',{name:new RegExp(dateLabel)}).click();
    await current.locator('.slot-option').first().waitFor({state:'visible',timeout:25000});
    await current.locator('.slot-option').first().click();
  }
  async function layout(path,width,height){
    await visit(path,width,height);
    // Visit the actual lazy media rather than treating offscreen placeholders as proof.
    await current.evaluate(async()=>{
      const distance=Math.max(400,innerHeight*.8);
      for(let y=0;y<document.documentElement.scrollHeight;y+=distance){scrollTo(0,y);await new Promise(resolve=>setTimeout(resolve,45));}
      scrollTo(0,0);
    });
    await current.waitForFunction(()=>[...document.querySelectorAll('main img')].every(img=>img.complete),{},{timeout:20000});
    await current.waitForFunction(()=>document.querySelector('.brand-logo')?.complete,{},{timeout:15000});
    await current.waitForTimeout(600);
    const detail=await current.evaluate(()=>({
      path:location.pathname,title:document.title,canonical:document.querySelector('link[rel=canonical]')?.href,
      description:document.querySelector('meta[name=description]')?.content,
      robots:document.querySelector('meta[name=robots]')?.content,
      h1:document.querySelectorAll('#page-content h1').length,
      headers:document.querySelectorAll('.sarsa-header').length,footers:document.querySelectorAll('.sarsa-footer').length,
      logo:(()=>{const node=document.querySelector('.sarsa-header .brand-logo');return node&&{src:node.getAttribute('src'),loaded:node.complete&&node.naturalWidth===128,alt:node.getAttribute('alt')};})(),
      favicon:document.querySelector('link[rel=icon]')?.getAttribute('href'),
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
    check(detail.logo?.loaded&&detail.logo.src==='/media/sarsa-kundli-lotus-logo-128.png'&&detail.logo.alt==='','Approved shared logo is missing, broken or duplicated in the accessible name');
    check(detail.favicon==='/media/sarsa-kundli-lotus-favicon.png','Approved favicon is missing');
    check(detail.overflow<=1,'Sideways overflow '+detail.overflow+'px');
    check(detail.title.includes('Sarsa')&&!detail.title.includes('Page not found'),'Missing route title');
    check(detail.canonical===origin+path,'Incorrect canonical '+detail.canonical);
    check(!!detail.description,'Missing description');
    check(detail.images.every(image=>image.loaded&&image.altPresent),'Broken image or missing alt attribute: '+JSON.stringify(detail.images.filter(image=>!image.loaded||!image.altPresent)));
    if(path==='/booking/receipt')check(detail.robots.includes('noindex'),'Private lookup must be noindex');
    if(path==='/about'||path.startsWith('/services')||path==='/contact'||path==='/testimonials'){
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
    if(phase==='edges')for(const [width,height] of [[320,740],[768,1024],[1920,1080]])for(const path of ['/','/about','/services','/services/prashna-kundali','/contact','/booking'])await run('edge '+path+' '+width,()=>layout(path,width,height));
    if(phase==='booking-layouts'){
      for(const [width,height] of [[390,844],[1440,900],[320,740],[768,1024],[1920,1080]])await run('Booking readiness /booking '+width,()=>layout('/booking',width,height));
      await run('Booking through review without submitting',async()=>{
        await visit('/booking');
        const response=await context.request.get(origin+'/api/booking-policy',{timeout:45000});check(response.status()===200,'Policy unavailable');const policy=await response.json();
        const {dateLabel}=await availableDay(policy,'kundli-matching',1);
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
      for(const width of [1440,390])await run('Approved Home/About identity and information '+width,async()=>{
        await current.emulateMedia({reducedMotion:'reduce'});await visit('/',width,width===390?844:900);
        check(await current.locator('main h1').innerText()==='Sarsa Jyotish Sansthan','Approved Home name missing');
        check(await current.locator('.hero-byline').innerText()==='by Madhuri Gupta','Approved person byline missing');
        check(await current.locator('.hero-experience').innerText()==='15+ years of experience','Confirmed experience missing');
        check(await current.locator('.hero-action').count()===2,'Both Home actions must remain');
        check(await current.locator('.hero-action.secondary').getAttribute('href')==='/contact','Question action destination changed');
        check(await current.locator('.service-choice').count()===services.length,'Quick services are incomplete');
        for(const service of services)check(await current.locator('.service-choice[href="/services/'+service+'"]').count()===1,'Quick service missing: '+service);
        check(await current.title()==='Astro Guidance by Madhuri Gupta | Sarsa Jyotish Sansthan','Home browser title differs from approval');
        await current.locator('.hero-meet').click();await current.waitForFunction(()=>location.hash==='#madhuri'&&Math.abs(document.querySelector('#madhuri').getBoundingClientRect().top)<20);
        check(await current.locator('.hero-meet').evaluate(node=>document.activeElement===node),'Pointer navigation should retain the activated link focus');
        await current.locator('.hero-meet').focus();await current.keyboard.press('Enter');
        await current.waitForFunction(()=>document.activeElement?.dataset.scrollDestination==='madhuri');
        check(await current.evaluate(()=>document.activeElement?.dataset.scrollDestination==='madhuri'),'Meet Madhuri must retain its measured scroll/focus destination');
        await visit('/about',width,width===390?844:900);
        check(await current.locator('main h1').innerText()==='Madhuri Gupta','Approved About name missing');
        check(await current.locator('.intro-role').innerText()==='Astro & Jyotish guidance','About role missing');
        const facts=await current.locator('[data-hero-band]').innerText();
        for(const text of ['15+','Jyotish Shastri','Jyotish Acharya','Shri Vedang Jyotish Sansthan','Bhrigu Nandi Nadi Astrology','Yogrishi Astro Research Institute'])check(facts.includes(text),'Approved fact missing: '+text);
        check(await current.locator('[data-enter]').count()===4,'About entry groups changed');
        check(await current.locator('#scene').evaluate(node=>node.offsetHeight)===(width<=650?940:660),'Original About scene size changed');
        check(await current.locator('[data-hero-band]').evaluate(node=>getComputedStyle(node).opacity)==='1','Facts must settle with reduced motion');
        check(await current.title()==='About Madhuri Gupta — Astro & Jyotish | Sarsa Jyotish Sansthan','About browser title differs from approval');
        return {width,quickServices:5,confirmedExperience:'15+',courseTitles:3};
      });
      await run('Home FAQs and back to top',async()=>{
        await visit('/');check(await current.locator('.service-grid article.service').count()===services.length,'Home is missing a service');check(await current.locator('.service--prashna a[href="/services/prashna-kundali"]').count()===1,'Home Prashna destination missing');const items=current.locator('.faq-list details');check(await items.count()===9,'Expected nine Home FAQs including approved Customer Reviews');check(await items.filter({hasText:'Can I read what other clients say?'}).locator('a[href="/testimonials"]').count()===1,'Approved Reviews FAQ destination missing');
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
        const rows=current.locator('.service-row');check(await rows.count()===services.length,'Missing service rows');
        check(await current.locator('.sarsa-certifications').count()===0,'Retired certificates are still shown');
        for(let i=0;i<services.length;i++){check(await rows.nth(i).locator('.row-actions a').count()===2,'Explore/Book pair missing');}
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
        check(await current.locator('input[name=service]').count()===services.length,'Missing live service choices');
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
        return {serviceCount:services.length,createdBooking:false,submittedDetails:false};
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
        await visit('/services');const cards=current.locator('[data-directory-card]');check(await cards.count()===services.length,'Expected five service cards');
        for(let i=0;i<services.length;i++){const card=cards.nth(i);await card.scrollIntoViewIfNeeded();check(await card.locator('.directory-photo img').count()===1,'Service photograph missing');check(await card.locator('.service-actions a').count()===2,'Explore/Book actions missing');
          const values=await card.locator('.service-actions').evaluate(node=>({alignment:getComputedStyle(node).justifyContent,weights:[...node.querySelectorAll('a')].map(a=>parseInt(getComputedStyle(a).fontWeight,10))}));
          check(values.alignment==='flex-end','Service buttons not right aligned');check(values.weights.every(weight=>weight>=600),'Service actions not emphasized');}
        const gap=await current.locator('.first-service-guide').evaluate(node=>({top:node.getBoundingClientRect().top,directoryBottom:document.querySelector('.service-directory').getBoundingClientRect().bottom}));check(gap.top-gap.directoryBottom>=40,'Divider touches service cards');
      });
      for(const service of illustratedServices)await run('Service illustrations '+service,async()=>{
        await visit('/services/'+service);const story=current.locator('.service-visual-story');await story.scrollIntoViewIfNeeded();
        const choices=story.locator('.story-choices button');check(await choices.count()===3,'Expected three explanation choices');
        for(let i=0;i<3;i++){await choices.nth(i).click();check(await choices.nth(i).getAttribute('aria-pressed')==='true','Topic selection not updated');check(await story.locator('.story-choices button[aria-pressed=true]').count()===1,'Multiple selected topics');}
        const first=await story.locator('.story-picture img').last().getAttribute('src');await story.getByRole('button',{name:'Next →',exact:true}).click();
        await story.locator('.story-controls').getByText('2 of 2',{exact:true}).waitFor({state:'visible',timeout:20000});
        const second=await story.locator('.story-picture img').last().getAttribute('src');check(first!==second,'Picture did not change');
        // The picture counter changes before the browser finishes selecting/loading srcset.
        // Wait for that real lifecycle; a completed broken image still fails the next assertion.
        await current.waitForFunction(source=>{const image=[...document.querySelectorAll('.service-visual-story .story-picture img')].at(-1);return image?.getAttribute('src')===source&&image.complete;},second,{timeout:20000});
        check(await story.locator('.story-picture img').last().evaluate(node=>node.complete&&node.naturalWidth>0),'Second picture failed to load');
        await story.getByRole('button',{name:'← Previous',exact:true}).click();await story.locator('.story-controls').getByText('1 of 2',{exact:true}).waitFor({state:'visible'});
        check(await story.locator('.story-picture img').last().getAttribute('src')===first,'Previous picture not restored');return {service,topics:3,pictures:2};
      });
    }
    if(phase==='prashna'){
      for(const [width,height] of [[390,844],[1440,900]])await run('Prashna booking quantity and fixed-service switch '+width,async()=>{
        await visit('/booking?service=prashna-kundali',width,height);
        const selected=current.locator('input[name=service][value="prashna-kundali"]');
        check(await selected.isChecked(),'Direct Prashna link did not select its enabled service');
        check(await current.locator('.booking-alert-actions').count()===0,'Enabled Prashna still reports unavailable');
        const card=current.locator('.service-card--prashna');await card.scrollIntoViewIfNeeded();
        await current.waitForFunction(()=>{const img=document.querySelector('.service-card--prashna img');return img?.complete&&img.naturalWidth>0;});
        check((await card.innerText()).includes('per question'),'Card does not explain unit pricing');
        const quantity=current.locator('#question-count');
        check((await quantity.locator('option').evaluateAll(options=>options.map(o=>o.value))).join(',')==='1,2,3,4,5,6,7,8,9,10','Count choices differ from1–10');
        const totals=[];
        for(const count of [1,3,10]){
          await quantity.selectOption(String(count));
          const expected=new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(count*1100);
          await current.waitForFunction(value=>document.querySelector('.amount-plaque strong')?.textContent===value,expected);
          check((await current.locator('#question-count-hint').innerText()).includes('One 30-minute appointment'),'Count incorrectly changes appointment duration');
          totals.push({questions:count,total:await current.locator('.amount-plaque strong').innerText()});
        }
        check(await current.evaluate(()=>document.documentElement.scrollWidth-innerWidth)<=1,'Prashna booking overflows on '+width);
        await current.locator('.service-card').filter({has:current.locator('input[value="kundli-matching"]')}).click();
        check(await quantity.count()===0,'Fixed service kept the quantity selector');
        check(await current.locator('.summary-row').filter({hasText:'Questions'}).count()===0,'Fixed service kept question pricing');
        check((await current.locator('.amount-plaque strong').innerText())==='₹2,100','Fixed service price multiplied after switch');
        check(await current.locator('.submit-button').isDisabled(),'Payment became available without a complete appointment');
        return {width,totals,fixedServiceRestored:true,submitted:false};
      });
      await run('Prashna native topics, FAQs and fee examples',async()=>{
        await visit('/services/prashna-kundali');
        check(await current.locator('[data-prashna-scene]').count()===6,'Missing Prashna sections');
        const tabs=current.getByRole('tab');check(await tabs.count()===3,'Missing question topics');
        for(let i=0;i<3;i++){await tabs.nth(i).click();check(await tabs.nth(i).getAttribute('aria-selected')==='true','Topic selection missing');check(await current.getByRole('tabpanel').locator('.example-sheet').count()===2,'Expected two examples per topic');}
        await tabs.first().focus();await current.keyboard.press('End');check(await tabs.last().getAttribute('aria-selected')==='true','End did not select final topic');
        await current.keyboard.press('ArrowRight');check(await tabs.first().getAttribute('aria-selected')==='true','Topic keyboard wrap failed');
        const faqs=current.locator('details[name="prashna-faq"]');check(await faqs.count()===5,'Missing Prashna FAQs');
        await faqs.nth(0).locator('summary').click();await faqs.nth(1).locator('summary').click();
        check(await current.locator('details[name="prashna-faq"][open]').count()===1,'Prashna FAQs are not exclusive');
        const fees=await current.locator('.amount-example').allTextContents();
        check(fees.join(' ').includes('₹1,100')&&fees.join(' ').includes('₹3,300')&&fees.join(' ').includes('₹11,000'),'Fee examples are incorrect');
        return {sections:6,topics:3,examplesPerTopic:2,faqs:5};
      });
      await run('Prashna assembly, ambient pause and reduced movement',async()=>{
        await current.emulateMedia({reducedMotion:'no-preference'});await current.mouse.move(0,0);await visit('/services/prashna-kundali');
        await current.waitForFunction(()=>document.querySelector('.prashna-hero')?.dataset.motionProgress==='1.000',{},{timeout:10000});
        const ambient=current.locator('.prashna-art-stage [data-ambient-part="note"]');
        const before=await ambient.evaluate(el=>getComputedStyle(el).transform);await current.waitForTimeout(400);const after=await ambient.evaluate(el=>getComputedStyle(el).transform);
        check(before!==after,'Settled Prashna artwork is not looping');
        await current.locator('.prashna-art-stage').hover();await current.waitForTimeout(50);
        const paused=await ambient.evaluate(el=>getComputedStyle(el).transform);await current.waitForTimeout(300);
        check(paused===await ambient.evaluate(el=>getComputedStyle(el).transform),'Artwork does not pause on hover');
        await current.emulateMedia({reducedMotion:'reduce'});
        check(await ambient.evaluate(el=>getComputedStyle(el).animationName)==='none','System reduced motion is not respected');
        return {heroSettled:true,ambientMoves:true,hoverPauses:true,reducedMotionStops:true};
      });
      await run('Prashna through review and quantity invalidation without submitting',async()=>{
        await visit('/booking?service=prashna-kundali');
        const response=await context.request.get(origin+'/api/booking-policy',{timeout:45000});check(response.status()===200,'Policy unavailable');const policy=await response.json();
        await current.locator('#question-count').selectOption('3');
        const selected=await availableDay(policy,'prashna-kundali',3);await chooseDate(selected.dateLabel);
        await current.getByRole('button',{name:'Fill your details →',exact:true}).click();
        await current.locator('#full_name').fill('Read-only Browser Check');await current.locator('#phone').fill('0000000000');
        await current.getByRole('button',{name:'Review your booking →',exact:true}).click();
        const summary=await current.locator('.summary-sheet').innerText();
        check(summary.includes('Prashna Kundali')&&summary.includes('3 × ₹1,100')&&summary.includes('₹3,300'),'Prashna review lost count/unit/total');
        check(summary.includes('30 minutes · Google Meet'),'Prashna appointment is not one30-minute Google Meet');
        check(await current.locator('.submit-button').isDisabled(),'Payment active without acknowledgement');
        await current.locator('#question-count').selectOption('10');
        check(await current.locator('input[name=time]:checked').count()===0,'Quantity change kept the previous selected time');
        check(await current.locator('.submit-button').isDisabled(),'Quantity change left payment enabled');
        await current.waitForFunction(()=>document.querySelector('.amount-plaque strong')?.textContent==='₹11,000');
        return {day:selected.day,questions:3,reachedReview:true,amountPaise:330000,selectedTimeClearedOnCountChange:true,customerDetailsSubmitted:false,bookingCreated:false};
      });
    }
    if(phase==='links'){
      const payload=fragment.slice(phase.length+1);check(!!payload,'Links phase needs the actual collected public targets');
      const targets=[...new Set(JSON.parse(decodeURIComponent(payload)))];check(targets.length>0,'No observed internal links supplied');
      for(const target of targets)await run('Internal link '+target,async()=>{
        const url=new URL(target);check(url.origin===origin,'Unexpected external target');
        const response=await context.request.get(url.href,{timeout:45000});check(response.status()===200,'Internal destination HTTP '+response.status());
        if(url.hash){await current.goto(url.href,{waitUntil:'domcontentloaded',timeout:45000});await current.locator('#page-content h1').waitFor({state:'visible',timeout:30000});check(await current.locator('[id]').evaluateAll((nodes,id)=>nodes.some(n=>n.id===id),decodeURIComponent(url.hash.slice(1))),'Internal anchor is missing: '+url.hash);}
        return {url:target,http:200,anchorChecked:!!url.hash};
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
        if(path==='/api/booking-policy'){policy=data;check(data.policy.services.length===services.length,'Policy missing services');check(data.policy.services.map(s=>s.id).sort().join(',')===[...services].sort().join(','),'Unexpected service identities');for(const s of data.policy.services){check(s.enabled===true,'Expected service disabled: '+s.id);check(s.duration_minutes===30,'Appointment duration changed: '+s.id);if(s.id==='prashna-kundali'){check(s.pricing.kind==='per_question'&&s.pricing.amount_paise===110000&&s.pricing.maximum_questions===10,'Incorrect Prashna pricing/count');check(s.required_preparation.length===0,'Unexpected required Prashna preparation');}else check(s.pricing.kind==='fixed'&&s.pricing.amount_paise===fixedFees[s.id],'Original service fee changed: '+s.id);}check(data.policy.meeting==='google_meet','Meeting arrangement changed');check(data.policy.required_contacts.includes('phone'),'Phone not required');check(data.policy.booking_verification.email===false,'Email verification differs from saved OFF choice');}
        return {path,http:response.status(),noStore:true};
      });
      if(policy){const tomorrow=new Date(Date.parse(policy.server_now)+86400000);const day=new Intl.DateTimeFormat('en-CA',{timeZone:policy.policy.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(tomorrow);
        for(const service of services)await run('Availability '+service,async()=>{const response=await context.request.get(origin+'/api/availability?'+new URLSearchParams({service_id:service,day,questions:'1'}),{timeout:45000});check(response.status()===200,'Availability HTTP '+response.status());const data=await response.json();check(Array.isArray(data.slots),'Availability has no slots array');return {service,day,availableSlots:data.slots.length};});}
      if(policy){
        let selectedDate;
        for(const count of [1,3,10])await run('Prashna server quantity '+count,async()=>{
          selectedDate??=availableDay(policy,'prashna-kundali',1);const selected=await selectedDate;
          const response=await context.request.get(origin+'/api/availability?'+new URLSearchParams({service_id:'prashna-kundali',day:selected.day,questions:String(count)}),{timeout:45000});
          check(response.status()===200,'Prashna availability HTTP '+response.status());const data=await response.json(),quote=data.service;
          check(quote.questions===count&&quote.amount_paise===110000*count,'Server count/fee total mismatch');
          check(quote.duration_minutes===30&&quote.meeting==='google_meet','Count changed appointment duration or platform');
          check(quote.quote_version===policy.quote_version,'Quote is not bound to the current live policy');
          check(data.slots.length>0,'No slots on the inspected available day');check(data.slots.every(slot=>Date.parse(slot.ends_at)-Date.parse(slot.starts_at)===30*60000),'A Prashna slot is not30 minutes');
          return {questions:count,amountPaise:quote.amount_paise,durationMinutes:quote.duration_minutes,day:selected.day,slots:data.slots.length};
        });
      }
      const retired=['/certificate.webp',...['jyotish-shastri','jyotish-acharya','astro-research-institute','trinity-vaastu-numerology'].flatMap(name=>['preview.webp','full.webp','original.'+(name==='astro-research-institute'?'pdf':'jpeg')].map(file=>'/media/certificates/'+name+'-'+file))];
      for(const path of retired)await run('Retired certificate '+path,async()=>{const response=await context.request.get(origin+path,{maxRedirects:0,timeout:45000});check(response.status()===404,'Retired certificate is still published');return {path,http:404};});
      await run('Public sitemap and robots',async()=>{
        const response=await context.request.get(origin+'/sitemap.xml');check(response.status()===200,'Sitemap unavailable');const xml=await response.text(),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match=>match[1]);
        const expected=paths.filter(path=>path!=='/booking/receipt');check(urls.length===expected.length,'Unexpected sitemap route count '+urls.length);check(expected.every(path=>urls.includes(origin+path)),'Public route absent from sitemap');
        check(!urls.some(url=>url.includes('/booking/receipt')||url.includes('/studio')||url.includes('/company')),'Private path indexed');
        const robots=await context.request.get(origin+'/robots.txt');check(robots.status()===200,'Robots unavailable');check((await robots.text()).includes('Sitemap: '+origin+'/sitemap.xml'),'Robots missing sitemap');return {publicRoutes:urls.length};
      });
      await run('Published Customer reviews page',async()=>{await visit('/testimonials');check(await current.locator('.chapter[data-scene]').count()===5,'Approved review chapters missing');check(await current.locator('.story-card').count()===6,'Initial review collection missing');await current.locator('#more-stories').click();check(await current.locator('.story-card').count()===12,'Approved twelve-account collection missing');check(await current.locator('.sarsa-header a[href="/testimonials"]').getAttribute('aria-current')==='page','Selected Reviews navigation missing');return {http:200,chapters:5,approvedReviews:12};});
      for(const path of ['/studio','/studio/calendar','/enquiries-studio','/company/booking-control','/company/booking-support','/company/google-repair'])await run('Private sign-in '+path,async()=>{const response=await context.request.get(origin+path,{maxRedirects:0,timeout:45000});check(response.status()===200,'Sign-in page HTTP '+response.status());check((response.headers()['x-robots-tag']||'').includes('noindex'),'Private entry permits indexing');const body=await response.text();check(/sign.in|log.in|password|continue with google/i.test(body),'Missing sign-in boundary');return {path,http:200,signedIn:false};});
      await run('Unknown page',async()=>{const response=await context.request.get(origin+'/sarsa-hosted-check-page-does-not-exist',{maxRedirects:0});check(response.status()===404,'Unknown page does not return 404');return {http:404};});
    }
  } finally {
    await context.close();report.finished=new Date().toISOString();report.assertions=assertions;report.internalLinks=[...new Set(report.internalLinks)];report.assets=[...new Set(report.assets)];report.warnings=[...new Set(report.warnings)];report.externalFailures=[...new Map(report.externalFailures.map(item=>[JSON.stringify(item),item])).values()];
  }
  report.passed=report.cases.filter(item=>item.status==='passed').length;report.failed=report.cases.filter(item=>item.status==='failed').length;
  return report;
}
