async page=>{
 const browser=page.context().browser(), results=[];
 for(const mode of ['blocked-storage','another-booking']){
  const context=await browser.newContext({viewport:{width:390,height:844}}),p=await context.newPage();let calls=0;
  await context.addInitScript(mode=>{if(mode==='blocked-storage'){Storage.prototype.setItem=function(){throw Error('blocked');};}else{sessionStorage.setItem('sarsa:004:booking-receipt:v1',JSON.stringify({version:1,request_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',secret:'A'.repeat(43)}));}},mode);
  await context.route('**/api/checkout/**',async route=>{calls++;await route.abort();});
  try{await p.goto('http://127.0.0.1:3018/booking-help');await p.locator('#recovery-reference').fill('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');await p.locator('#recovery-code').fill('12345678');await p.getByRole('button',{name:'Restore booking access',exact:true}).click();await p.getByText(mode==='blocked-storage'?/cannot safely save/:/Another booking is saved/).waitFor();if(calls!==0)throw Error('Redemption attempted without safe storage');if(mode==='another-booking'&&(await p.evaluate(()=>JSON.parse(sessionStorage.getItem('sarsa:004:booking-receipt:v1')).request_id))!=='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')throw Error('Existing booking overwritten');results.push(mode);}finally{await context.close();}
 }
 return {passed:true,cases:results,noProviderRequests:true};
}
