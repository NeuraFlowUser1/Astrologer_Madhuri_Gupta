import {test} from 'node:test';
import assert from 'node:assert/strict';
import {staffFixture,available,id,waitText,within} from './staff-page-fixture.mjs';
test('staff connection status distinguishes absent, expired and prepared records with exact Google links',{skip:!available},()=>staffFixture(async(page,state)=>{
 assert.equal(await page.locator('#prepare-workbook').isVisible(),false);
 state.status.authorization_saved=true;await page.reload();await page.locator('#prepare-workbook').waitFor();assert.match(await page.locator('#workbook-status').textContent(),/Create your separate/);
 state.handlers.set('/api/studio/workbook/prepare',({reply})=>{state.status.workbook_url='https://docs.google.com/spreadsheets/d/fixture_owned';reply({code:'ready'});});
 await page.click('#prepare-workbook');await page.locator('#open-workbook').waitFor();assert.equal(await page.locator('#open-workbook').getAttribute('href'),'https://docs.google.com/spreadsheets/d/fixture_owned');assert.equal(await page.locator('#prepare-workbook').isVisible(),false);
 state.status.reconnect_required=true;state.status.resources=[{resource:'calendar',connected:true}];delete state.status.workbook_url;await page.reload();await waitText(page,'#connection-status','permission has expired');assert.equal(await page.locator('#connect').textContent(),'Reconnect Calendar');assert.equal(await page.locator('#connect-records').textContent(),'Reconnect my records');assert.equal(await page.locator('#prepare-workbook').isVisible(),false);
}));
test('unexpected spreadsheet and authorization destinations are refused without leaving the staff origin',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 for(const url of ['https://example.test/spreadsheets/d/fixture','https://docs.google.com/spreadsheets/d/fixture?token=private','https://docs.google.com/spreadsheets/d/fixture#fragment','https://docs.google.com/other/fixture']){
  state.status.workbook_url=url;await page.reload();await waitText(page,'#status','cannot check');assert.equal(await page.locator('#open-workbook').isVisible(),false);
 }
 delete state.status.workbook_url;await page.reload();await waitText(page,'#status','You are signed in');
 state.handlers.set('/api/studio/resources/start',({reply})=>reply({authorization_url:'https://example.test/collect'}));await page.click('#connect');await waitText(page,'#status','could not start');assert.equal(page.url(),origin+'/studio');
 await page.click('#connect-records');await waitText(page,'#status','could not start');assert.equal(state.calls.filter(x=>x.path.endsWith('/resources/start')).at(-1).body.resource,'client_sheet');
}));
test('staff signout and sign-in failures stay recoverable without inventing an active session',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 state.handlers.set('/api/studio/logout',({reply})=>reply({code:'unavailable'},503));await page.click('#logout');await waitText(page,'#status','Sign-out could not be confirmed');
 state.handlers.set('/api/studio/logout',({reply})=>{state.status={signed_in:false};reply({code:'signed_out'});});await page.click('#logout');await page.locator('#signin-panel').waitFor();assert.equal(await page.locator('#connection-panel').isVisible(),false);assert.equal(await page.locator('#calendar-panel').isVisible(),false);
 state.handlers.set('/api/studio/sign-in/start',({reply})=>reply({authorization_url:'https://accounts.google.com/incorrect-path'}));await page.locator('[data-role=client]').click();await waitText(page,'#status','could not start');assert.equal(page.url(),origin+'/studio');
 state.handlers.set('/api/studio/status',({reply})=>reply({code:'access_unavailable'},401));await page.click('#retry');await waitText(page,'#status','Start by signing in');assert.equal(await page.locator('#signin-panel').isVisible(),true);
}));
test('interrupted workbook preparation is checked on refresh and connection warnings are cleared from the URL',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 state.status.authorization_saved=true;state.handlers.set('/api/studio/workbook/prepare',({reply})=>reply({code:'unknown'},503));await page.reload();await page.locator('#prepare-workbook').waitFor();await page.click('#prepare-workbook');await waitText(page,'#status','look for the existing spreadsheet');
 state.status.workbook_url='https://docs.google.com/spreadsheets/d/fixture_owned';await page.click('#retry');await page.locator('#open-workbook').waitFor();assert.equal(state.calls.filter(x=>x.path.endsWith('/workbook/prepare')).length,1);
 await page.goto(origin+'/studio?connection=failed');await waitText(page,'#status','previously saved connection has not been replaced');assert.equal(page.url(),origin+'/studio');
 await page.goto(origin+'/studio?connection=check');await waitText(page,'#status','connection was interrupted');assert.equal(page.url(),origin+'/studio');
}));
test('Google return finishes one pending permission and refuses an unconfirmed finish',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 state.handlers.set('/api/studio/resources/finish',({reply})=>reply({code:'saved'}));await page.goto(origin+'/studio?fixture-return=1#google-consent='+id+'.pending');await waitText(page,'#status','You are signed in');assert.equal(state.calls.filter(x=>x.path.endsWith('/resources/finish')).length,1);assert.equal(page.url(),origin+'/studio');
 state.handlers.set('/api/studio/resources/finish',({reply})=>reply({code:'unknown'}));await page.goto(origin+'/studio?fixture-return=1#google-consent='+id+'.pending');await waitText(page,'#status','cannot check');assert.equal(await page.locator('#retry').isVisible(),true);
}));
test('late account response after booking is switched off cannot redisplay the booking dashboard',{skip:!available},()=>staffFixture(async(page,state)=>{
 let release,arrived;const started=new Promise(resolve=>{arrived=resolve;});state.handlers.set('/api/studio/status',async({reply})=>{await new Promise(resolve=>{release=resolve;arrived();});reply(state.status);});
 const loading=page.evaluate(()=>load());await started;state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));release();await loading;
 assert.equal(await page.locator('[data-booking-shell]').isVisible(),false);assert.equal(await page.locator('#connection-panel').isVisible(),false);assert.equal(await page.locator('#calendar-panel').isVisible(),false);
}));
test('valid Google destination is followed only after the correct owner permission request',{skip:!available},()=>staffFixture(async(page,state)=>{
 await page.route('https://accounts.google.com/**',route=>route.fulfill({status:200,contentType:'text/html',body:'Synthetic Google consent destination; no provider request.'}));
 state.handlers.set('/api/studio/resources/start',({reply})=>reply({authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic'}));await page.click('#connect');await page.waitForURL('https://accounts.google.com/o/oauth2/v2/auth?state=synthetic');assert.equal(state.calls.filter(x=>x.path.endsWith('/resources/start')).at(-1).body.resource,'calendar');
}));
test('failed or unexpected status cannot invent a client login, and retry uses the current saved state',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.status={signed_in:true,role:'agency'};await page.reload();await waitText(page,'#status','cannot check');assert.equal(await page.locator('#calendar-panel').isVisible(),false);
 state.handlers.set('/api/studio/status',({reply})=>reply({code:'unavailable'},503));await page.click('#retry');await waitText(page,'#status','cannot check');assert.equal(await page.locator('#signin-panel').isVisible(),false);
 state.handlers.delete('/api/studio/status');state.status={signed_in:false};await page.click('#retry');await waitText(page,'#status','Start by signing in');assert.equal(await page.locator('#signin-panel').isVisible(),true);
}));
test('switching off during Google consent completion cannot show the dashboard again',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 let finish,arrived;const started=new Promise(resolve=>{arrived=resolve;});state.handlers.set('/api/studio/resources/finish',({reply})=>{finish=()=>reply({code:'saved'});arrived();});await page.goto(origin+'/studio?fixture-return=2#google-consent='+id+'.pending');await started;
 state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);assert.equal(await page.locator('#connection-panel').isVisible(),false);assert.equal(await page.locator('#calendar-panel').isVisible(),false);
}));
test('a Google-start reply arriving after OFF cannot navigate the customer away',{skip:!available},()=>staffFixture(async(page,state,origin)=>{
 let finish,arrived;const started=new Promise(resolve=>{arrived=resolve;});state.handlers.set('/api/studio/resources/start',({reply})=>{finish=()=>reply({authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic'});arrived();});await page.click('#connect');await started;state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);assert.equal(page.url(),origin+'/studio');assert.equal(await page.locator('#connection-panel').isVisible(),false);
}));
for(const path of ['workbook/prepare','logout'])for(const rejected of [false,true])test(`late ${path} ${rejected?'failure':'success'} cannot revive staff controls after OFF`,{skip:!available},()=>staffFixture(async(page,state)=>{
 state.status.authorization_saved=true;await page.reload();await page.locator('#prepare-workbook').waitFor();
 const received=Promise.withResolvers();state.handlers.set('/api/studio/'+path,({reply})=>received.resolve(()=>reply({code:rejected?'unknown':'ready'},rejected?503:200)));
 await page.click(path==='logout'?'#logout':'#prepare-workbook');const finish=await within(received.promise);
 state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);
 assert.equal(await page.locator('#connection-panel').isVisible(),false);assert.equal(await page.locator('#calendar-panel').isVisible(),false);assert.equal(await page.locator('[data-booking-shell]').isVisible(),false);
 assert.equal(state.calls.filter(x=>x.path==='/api/studio/'+path).length,1);
}));
test('failed Google-start after OFF does not replace the current page state with a stale connection error',{skip:!available},()=>staffFixture(async(page,state)=>{
 const received=Promise.withResolvers();state.handlers.set('/api/studio/resources/start',({reply})=>received.resolve(()=>reply({code:'unknown'},503)));
 await page.click('#connect');const finish=await within(received.promise);state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));
 const message=await page.locator('#status').textContent();finish();await page.waitForTimeout(50);assert.equal(await page.locator('#status').textContent(),message);assert.equal(await page.locator('#connection-panel').isVisible(),false);
}));
test('repeated form and connection actions while work is pending create only one request',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.status.authorization_saved=true;await page.reload();await page.locator('#prepare-workbook').waitFor();
 const received=Promise.withResolvers();state.handlers.set('/api/studio/workbook/prepare',({reply})=>received.resolve(()=>reply({code:'unknown'},503)));
 await page.click('#prepare-workbook');const finish=await within(received.promise);
 await page.evaluate(()=>{for(const id of ['prepare-workbook','connect','logout','retry'])document.querySelector('#'+id).dispatchEvent(new Event('click'));});
 finish();await waitText(page,'#status','look for the existing spreadsheet');
 assert.equal(state.calls.filter(x=>x.path==='/api/studio/workbook/prepare').length,1);
 assert.equal(state.calls.filter(x=>x.path==='/api/studio/resources/start'||x.path==='/api/studio/logout').length,0);
}));
