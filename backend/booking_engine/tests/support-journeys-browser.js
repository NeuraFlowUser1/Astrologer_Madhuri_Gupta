async page => {
  const fixture = __SARSA_SYNTHETIC_FIXTURE__;
  const origin = 'https://localhost:3039';
  const context = await page.context().browser().newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  const staff = await context.newPage(),errors=[],responses=[];
  staff.on('pageerror',error=>errors.push(error.message));
  // Only the third-party identity response is substituted. Every application
  // request below reaches the actual HTTP server and committed PostgreSQL data.
  await context.route('https://accounts.google.com/o/oauth2/v2/auth*',async route=>{
    const url=new URL(route.request().url()),role=url.searchParams.get('login_hint');
    if(!['client','agency'].includes(role))throw Error('Unexpected synthetic identity');
    const callback=new URL('/api/studio/sign-in/callback',origin);
    callback.searchParams.set('state',url.searchParams.get('state'));
    callback.searchParams.set('code','synthetic-'+role);
    await route.fulfill({status:302,headers:{location:callback.href},body:''});
  });
  staff.on('response',async response=>{
    if(response.url().endsWith('/appointments/support'))responses.push(await response.json());
  });
  const customer=await context.newPage();
  const post=async(p,path,body,secret)=>p.evaluate(async({path,body,secret})=>{
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json',...(secret?{'X-Booking-Receipt':secret}:{})},body:JSON.stringify(body)});
    return {status:r.status,data:await r.json()};
  },{path,body,secret});
  try{
    await staff.goto(origin+'/studio');
    await staff.locator('[data-role="client"]').click();
    await staff.locator('#calendar-panel').waitFor({state:'visible'});
    if(!await staff.getByText('You are signed in.',{exact:true}).isVisible())throw Error('Staff not signed in');
    for(const item of fixture.fixtures){
      await staff.locator('#booking-reference').fill(item.reference);
      await staff.getByRole('button',{name:'Find booking',exact:true}).click();
      await staff.locator('#booking-support-change').waitFor({state:'visible'});
      await staff.locator('#support-action').selectOption(item.kind==='correction'?'contact_correction':'receipt_recovery');
      if(item.kind==='correction'){
        await staff.locator('#support-email').fill('corrected@example.com');
        await staff.locator('#support-phone').fill('+919876543211');
      }
      await staff.locator('#support-payment').fill(item.payment);
      await staff.locator('#support-reason').fill('Approved synthetic support test; no real call or payment');
      await staff.locator('#support-verified').check();
      await staff.getByRole('button',{name:'Save verified support action',exact:true}).click();
      await staff.locator('#support-code-result').waitFor({state:'visible'});
      const code=await staff.locator('#support-code').textContent();
      if(!/^\d{8}$/.test(code))throw Error('Recovery code not displayed');
      await customer.goto(origin+'/booking-help');
      await customer.evaluate(()=>sessionStorage.clear());
      await customer.reload();
      const old=await post(customer,'/api/checkout/status',{request_id:item.reference},item.old_secret);
      if(item.kind==='correction'&&old.status!==403)throw Error('Old contact access not closed: '+old.status);
      if(item.kind==='receipt'&&![200,403].includes(old.status))throw Error('Unexpected old-access state: '+old.status);
      await customer.locator('#recovery-reference').fill(item.reference);
      await customer.locator('#recovery-code').fill(code);
      await customer.locator('#recovery-form button[type="submit"]').click();
      await customer.locator('#recovery-open').waitFor({state:'visible'});
      const restored=await customer.evaluate(()=>JSON.parse(sessionStorage.getItem('sarsa:004:booking-receipt:v1')));
      if(restored?.request_id!==item.reference)throw Error('Restored access not retained');
      const saved=await post(customer,'/api/checkout/status',{request_id:item.reference},restored.secret);
      if(saved.status!==200||saved.data.appointment_state!=='confirmed')throw Error('New access does not open original appointment');
      const replaced=await post(customer,'/api/checkout/status',{request_id:item.reference},item.old_secret);
      if(replaced.status!==403)throw Error('Old receipt access survived code redemption');
      await staff.locator('#booking-support').screenshot({path:'/tmp/sarsa-completion-check/'+item.kind+'-staff.png'});
      await customer.screenshot({path:'/tmp/sarsa-completion-check/'+item.kind+'-customer.png'});
    }
    await staff.locator('#calendar-day').fill(fixture.day);
    await staff.locator('#calendar-view button[type="submit"]').click();
    await staff.locator('#closure-start').fill(fixture.day+'T11:00');
    await staff.locator('#closure-end').fill(fixture.day+'T11:30');
    await staff.locator('#closure-reason').fill('Synthetic reopening check');
    await staff.locator('#calendar-close button[type="submit"]').click();
    await staff.getByRole('button',{name:'Make this time available',exact:true}).click();
    await staff.locator('#reopen-reason').fill('Synthetic test finished');
    await staff.locator('#calendar-reopen button[type="submit"]').click();
    await staff.getByText('That unavailable period is now open again. Normal booking hours still apply.',{exact:true}).waitFor();
    await staff.locator('#calendar-panel').screenshot({path:'/tmp/sarsa-completion-check/reopened-calendar.png'});
    if(errors.length)throw Error(errors.join(';'));
    return {passed:true,realHttpAndPostgres:true,syntheticGoogleIdentity:true,receiptReplaced:true,
            contactsCorrected:true,recoveryRedeemed:true,blockedTimeReopened:true,supportActions:responses.length};
  }finally{await context.close();}
}
