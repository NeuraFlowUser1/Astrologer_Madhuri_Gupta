/** Isolated visual/interaction checks. Only static files reach the local server. */
async page => {
  await page.unrouteAll({behavior:'wait'});
  let role='client', closed=false, failSave=false, savedBody=null, calls=0;
  const errors=[];const onError=e=>errors.push(e.message);page.on('pageerror',onError);
  const claim='11111111-1111-4111-8111-111111111111';
  const tomorrow=new Date(Date.now()+86400000).toISOString().slice(0,10);
  const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  await page.route('**/api/studio/status',route=>json(route,{signed_in:true,role,email:role==='client'?'sarsajyotish@gmail.com':'neuraflowindia@gmail.com',authorization_saved:false,reconnect_required:false,workbook_url:null}));
  await page.route('**/api/studio/calendar/*',route=>{
    const request=route.request();if(request.method()!=='POST')return route.continue();
    const path=new URL(request.url()).pathname,body=request.postDataJSON();
    if(path.endsWith('/list'))return json(route,{code:'ok',day:body.day,timezone:'Asia/Kolkata',next_cursor:null,items:closed?[{id:claim,kind:'closure',starts_at:tomorrow+'T10:00:00+05:30',ends_at:tomorrow+'T11:00:00+05:30',reason:'Personal commitment',name:null,service:null,state:null}]:[]});
    if(path.endsWith('/close')){
      calls++;if(savedBody&&JSON.stringify(savedBody)!==JSON.stringify(body))throw Error('Retry changed original request');savedBody=body;closed=true;
      if(failSave){failSave=false;return route.abort('failed');}return json(route,{code:calls===1?'closed':'existing',claim_id:claim,active:true});
    }
    if(path.endsWith('/reopen')){closed=false;return json(route,{code:'reopened',claim_id:claim});}
    return json(route,{code:'unavailable'},503);
  });
  await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:3016/studio');
  await page.getByText('No saved reservations or unavailable periods on this day.').waitFor();
  await page.locator('#calendar-day').fill(tomorrow);await page.getByRole('button',{name:'Show this day'}).click();
  await page.locator('#closure-start').fill(tomorrow+'T10:00');await page.locator('#closure-end').fill(tomorrow+'T11:00');
  await page.locator('#closure-reason').fill('Personal commitment');failSave=true;
  await page.getByRole('button',{name:'Block this time'}).click();
  await page.getByText('We could not confirm the change. Check the same saved request below.').waitFor();
  if(!(await page.locator('#closure-start').isDisabled()))throw Error('Uncertain request remained editable');
  await page.getByRole('button',{name:'Check the same change'}).click();
  await page.getByText('That time is now blocked. Existing appointments have not been changed.').waitFor();
  await page.getByRole('button',{name:'Make this time available',exact:true}).waitFor();
  if(calls!==2||!savedBody.starts_at.endsWith('+05:30'))throw Error('Retry/timezone contract failed');
  await page.locator('#calendar-panel').scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/sarsa-studio-calendar-desktop.png'});
  await page.getByRole('button',{name:'Make this time available',exact:true}).click();
  await page.locator('#reopen-reason').fill('Available again');
  await page.setViewportSize({width:390,height:844});await page.locator('#calendar-reopen').scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/sarsa-studio-calendar-phone.png'});
  await page.getByRole('button',{name:'Make time available',exact:true}).click();
  await page.getByText('That unavailable period is now open again. Normal booking hours still apply.').waitFor();
  await page.getByText('No saved reservations or unavailable periods on this day.').waitFor();
  await page.setViewportSize({width:320,height:800});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Narrow phone overflow');
  role='agency';await page.reload();await page.getByText('You are signed in.',{exact:true}).waitFor();
  if(await page.locator('#calendar-panel').isVisible())throw Error('Agency calendar visible');
  if(errors.length)throw Error(errors.join(';'));page.off('pageerror',onError);
  return {passed:true,closeRequests:calls,identicalRetry:true,agencyHidden:true,phoneWidths:[390,320]};
}
