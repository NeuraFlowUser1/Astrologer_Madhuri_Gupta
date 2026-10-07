import {test} from 'node:test';
import assert from 'node:assert/strict';
import {available,id,companyFixture,waitText} from './company-page-fixture.mjs';
const section=async(page,name)=>page.getByText(name,{exact:true}).click();
const business=async page=>{await section(page,'Prices, appointment lengths and working hours');await page.click('#load-business');await page.locator('#business-form').waitFor({state:'visible'});};
const submit=async page=>{await page.fill('#business-reason','Synthetic reviewed change');await page.click('#save-business');};

test('company mode keeps its exact saved operation after an unrelated successful reply',{skip:!available},()=>companyFixture(async(page,state)=>{
 state.handlers.set('/api/company/control/change',({reply})=>reply({snapshot:state.snapshot,progress:'effective',operation_id:id}));
 await page.click('#change');await waitText(page,'#status','response was interrupted');
 const first=state.calls.filter(c=>c.path==='/api/company/control/change').at(-1).body;
 await page.click('#change');await waitText(page,'#status','response was interrupted');
 assert.deepEqual(state.calls.filter(c=>c.path==='/api/company/control/change').at(-1).body,first);
 state.handlers.set('/api/company/control/change',({body,reply})=>reply({receipt:{operation_id:body.operation_id},current:{snapshot:{...state.snapshot,enabled:true},progress:'effective'}}));
 await page.click('#change');await waitText(page,'#status','Booking is on');
 assert.equal(await page.evaluate(()=>window.PracticeCompanyCommands.read('mode')),null);
}));

test('company business keeps its saved operation when the acknowledgement has a wrong revision',{skip:!available},()=>companyFixture(async(page,state)=>{
 await business(page);
 state.handlers.set('/api/company/settings',({req,reply})=>req.method==='GET'?reply(state.business):reply({saved:true,revision:'999',quote_version:'a'.repeat(64)}));
 await submit(page);await waitText(page,'#business-status','save could not be confirmed');
 const first=state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body;
 await page.click('#save-business');await waitText(page,'#business-status','save could not be confirmed');
 assert.deepEqual(state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body,first);
 assert.equal((await page.evaluate(()=>window.PracticeCompanyCommands.read('business'))).operation_id,first.operation_id);
}));

test('company business settings preserve exact money, optional question pricing and weekly windows',{skip:!available},()=>companyFixture(async(page,state)=>{
 await business(page);const fixed=page.locator('[data-service="fixed"]'),question=page.locator('[data-service="question"]');
 await fixed.locator('[data-part="price"]').fill('12.05');await fixed.locator('[data-part="duration"]').fill('45');await fixed.locator('[data-part="enabled"]').uncheck();
 await question.locator('[data-part="price"]').fill('3.5');await question.locator('[data-part="questions"]').fill('4');await page.check('#business-otp');await page.selectOption('#business-meeting','internal');
 await page.click('#add-window');const rows=page.locator('#business-windows > div');assert.equal(await rows.count(),2);
 await rows.last().locator('[data-part="weekday"]').selectOption('6');await rows.last().locator('[data-part="end"]').fill('24:00');await rows.first().getByRole('button',{name:'Remove',exact:true}).click();
 await submit(page);await waitText(page,'#business-status','Settings saved.');
 const saved=state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body;
 assert.equal(saved.settings.services[0].pricing.amount_paise,1205);assert.equal(saved.settings.services[0].enabled,false);assert.equal(saved.settings.services[0].duration_minutes,45);
 assert.equal(saved.settings.services[1].pricing.amount_paise,350);assert.equal(saved.settings.services[1].pricing.maximum_questions,4);
 assert.equal(saved.settings.booking_verification.email,true);assert.equal(saved.settings.meeting,'internal');
 assert.deepEqual(saved.settings.required_contacts,['email','phone']);
 assert.deepEqual(saved.settings.weekly_windows,[{weekday:6,start:'09:00',end:'24:00'}]);
 for(let n=0;n<30;n++)await page.click('#add-window');assert.equal(await rows.count(),28);
}));

test('changing the email-code choice changes only its email requirement and preserves other required contacts',{skip:!available},()=>companyFixture(async(page,state)=>{
 state.business.settings.required_contacts=['phone'];await business(page);
 for(const enabled of [true,false]){
  if(enabled)await page.check('#business-otp');else await page.uncheck('#business-otp');
  await submit(page);await waitText(page,'#business-status','Settings saved.');
  const saved=state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body;
  assert.equal(saved.settings.booking_verification.email,enabled);
  assert.deepEqual(saved.settings.required_contacts,enabled?['email','phone']:['phone']);
  await page.locator('#business-form').waitFor({state:'visible'});
 }
}));

test('company business rejects stale or invalid settings and preserves an uncertain save',{skip:!available},()=>companyFixture(async(page,state)=>{
 await business(page);
 for(const [status,text] of [[409,'Another change was saved first'],[422,'Check the prices, durations'],[503,'The save could not be confirmed']]){
  state.handlers.set('/api/company/settings',({req,reply})=>req.method==='GET'?reply(state.business):reply({code:'fixture_failure'},status));
  await submit(page);await waitText(page,'#business-status',text);
 }
 const old=state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body;
 state.handlers.set('/api/company/settings',({req,reply})=>req.method==='GET'?reply(state.business):reply({saved:false}));
 await page.click('#save-business');await waitText(page,'#business-status','The save could not be confirmed');
 assert.deepEqual(state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body,old);
 state.handlers.set('/api/company/settings',({reply})=>reply({code:'expired'},401));await page.click('#save-business');
 await waitText(page,'#status','Please sign in again');assert.equal(await page.locator('#business-services input').count(),0);assert.equal(await page.locator('#signed-in').isVisible(),false);
}));

test('company settings refuse malformed saved values and invalid money before mutation',{skip:!available},()=>companyFixture(async(page,state)=>{
 await section(page,'Prices, appointment lengths and working hours');
 state.handlers.set('/api/company/settings',({reply})=>reply({revision:'0',settings:{}}));await page.click('#load-business');await waitText(page,'#business-status','Settings could not be loaded');
 state.handlers.delete('/api/company/settings');await page.click('#load-business');await page.locator('#business-form').waitFor({state:'visible'});
 await page.locator('[data-service="fixed"] [data-part="price"]').fill('1e3');await page.fill('#business-reason','Synthetic invalid number');
 // Bypass only the browser's input validation to exercise the independent
 // application check; the page must still refuse a payment-setting request.
 await page.locator('#business-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitText(page,'#business-status','The save could not be confirmed');assert.equal(state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).length,0);
}));

test('company mode shows pending publication honestly and handles refusal without repeating a change',{skip:!available},()=>companyFixture(async(page,state)=>{
 state.progress='pending';await page.click('#refresh');await waitText(page,'#status','New bookings have stopped');await page.click('#change');await waitText(page,'#status','Turning booking on');
 state.handlers.set('/api/company/control/change',({reply})=>reply({code:'stale'},409));await page.click('#change');await waitText(page,'#status','Another change was saved first');
 assert.equal(await page.locator('#change').textContent(),'Turn booking off');
 state.handlers.set('/api/company/control/change',({reply})=>reply({code:'expired'},401));await page.click('#change');await waitText(page,'#status','Please sign in again');assert.equal(await page.locator('#signed-in').isVisible(),false);
}));

test('company password and sign-in failures clear entered passwords and do not claim success',{skip:!available},()=>companyFixture(async(page,state)=>{
 state.handlers.set('/api/company/sign-in/start',({reply})=>reply({code:'denied'},401));await page.fill('#username','synthetic.owner');await page.fill('#password','Synthetic browser password');await page.click('#login');await waitText(page,'#status','Sign-in failed');assert.equal(await page.inputValue('#password'),'');
 state.handlers.delete('/api/company/sign-in/start');await page.fill('#password','Synthetic browser password');await page.click('#login');await page.locator('#signed-in').waitFor({state:'visible'});
 await section(page,'Confirm or change your company password');
 for(const action of ['reauth','password']){
  const path=action==='reauth'?'/api/company/reauthenticate':'/api/company/password';
  for(const fail of [true,false]){
   if(fail)state.handlers.set(path,({reply})=>reply({code:'unavailable'},503));else state.handlers.delete(path);
   await page.fill(action==='reauth'?'#reauth-password':'#old-password','Synthetic existing password');if(action==='password')await page.fill('#new-password','Synthetic replacement password');
   await page.click('#'+action+'-submit');await waitText(page,'#credential-status',fail?(action==='reauth'?'Confirmation failed':'could not be confirmed'):(action==='reauth'?'Password confirmed':'Password changed'));
   for(const key of ['reauth-password','old-password','new-password'])assert.equal(await page.inputValue('#'+key),'');
  }
 }
 state.handlers.set('/api/company/sign-out',({reply})=>reply({code:'unavailable'},503));await page.click('#logout');await waitText(page,'#status','Sign-out could not be confirmed');
 state.handlers.set('/api/company/control/status',({reply})=>reply({},503));await page.click('#refresh');await waitText(page,'#status','could not check its saved state');
 state.handlers.delete('/api/company/sign-out');await page.click('#logout');await waitText(page,'#status','You are signed out');
},{login:false}));

test('company issue references validate project and fields and render only bounded safe descriptions',{skip:!available},()=>companyFixture(async(page,state)=>{
 await page.click('#load-incidents');await waitText(page,'#incident-status','does not prove');
 const row={operation:'control',code:'unexpected_failure',last_reference:id,occurrences:2,last_seen_at:'2031-04-04T10:00:00Z'};
 state.handlers.set('/api/company/operations/incidents',({reply})=>reply({version:1,project:'fixture',incidents:Array.from({length:25},()=>({...row}))}));await page.click('#load-incidents');await waitText(page,'#incident-status','latest 20 groups');assert.equal(await page.locator('#incident-list article').count(),20);
 for(const changed of [{operation:'<script>'},{code:'unknown'},{last_reference:'bad'},{occurrences:0},{last_seen_at:'bad'}]){
  state.handlers.set('/api/company/operations/incidents',({reply})=>reply({version:1,project:'fixture',incidents:[{...row,...changed}]}));await page.click('#load-incidents');await waitText(page,'#incident-status','could not be loaded');assert.equal(await page.locator('#incident-list article').count(),0);
 }
 state.handlers.set('/api/company/operations/incidents',({reply})=>reply({version:1,project:'foreign',incidents:[row]}));await page.click('#load-incidents');await waitText(page,'#incident-status','could not be loaded');
 state.handlers.set('/api/company/operations/incidents',({reply})=>reply({code:'expired'},401));await page.click('#load-incidents');await waitText(page,'#status','Please sign in again');assert.equal(await page.locator('#signed-in').isVisible(),false);
}));

test('company Google approvals stay separate and unexpected destinations never open',{skip:!available},()=>companyFixture(async(page,state)=>{
 await section(page,'Google connections and record copies');let pending=true;
 state.handlers.set('/api/company/resources/status',({reply})=>reply({resources:[{resource:'calendar',connected:true},{resource:'client_sheet',reconnect_required:true},{resource:'agency_sheet',connected:false}],pending:pending?[{resource:'client_sheet',attempt_id:id}]:[]}));
 await page.click('#google-refresh');await waitText(page,'#google-status','Client Calendar: connected');await waitText(page,'#google-status','approval needed');await waitText(page,'#google-status','NeuraFlow record copy: not connected');
 state.handlers.set('/api/company/resources/finish',({reply})=>reply({code:'not_saved'}));await page.getByRole('button',{name:'Finish Client records connection',exact:true}).click();await waitText(page,'#google-status','could not be installed');
 state.handlers.set('/api/company/resources/finish',({body,reply})=>{assert.equal(body.attempt_id,id);pending=false;reply({code:'saved'});});await page.getByRole('button',{name:'Finish Client records connection',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#google-pending').children.length===0);
 for(const destination of ['https://foreign.invalid/o/oauth2/v2/auth','https://accounts.google.com/wrong','not a URL']){
  state.handlers.set('/api/company/resources/start',({reply})=>reply({authorization_url:destination}));await page.locator('[data-google-resource="calendar"]').click();await waitText(page,'#google-status','could not start');
 }
 state.handlers.set('/api/company/resources/status',({reply})=>reply({},503));await page.click('#google-refresh');await waitText(page,'#google-status','could not be checked');
 await page.click('#record-refresh');await waitText(page,'#record-status','No spreadsheet update problems');
}));

test('company permission loss clears settings and rejects a late private reply',{skip:!available},()=>companyFixture(async(page,state)=>{
 await business(page);let release;const arrived=new Promise(resolve=>state.handlers.set('/api/company/settings',({reply})=>{release=()=>reply(state.business);resolve();}));
 await page.click('#load-business');await arrived;
 state.handlers.set('/api/company/operations/incidents',({reply})=>reply({code:'forbidden'},403));await page.click('#load-incidents');await waitText(page,'#status','Please sign in again');
 const finished=page.waitForResponse(response=>response.url().endsWith('/api/company/settings'));release();await (await finished).finished();await page.waitForLoadState('networkidle');
 assert.equal(await page.locator('#business-services input').count(),0);assert.equal(await page.locator('#business-form').isVisible(),false);
 assert.equal(await page.locator('#signed-in').isVisible(),false);
}));

test('company Google approval reply cannot navigate after sign-out',{skip:!available},()=>companyFixture(async(page,state,origin)=>{
 await section(page,'Google connections and record copies');let release;const arrived=new Promise(resolve=>state.handlers.set('/api/company/resources/start',({reply})=>{release=()=>reply({authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic'});resolve();}));
 await page.locator('[data-google-resource="calendar"]').click();await arrived;await page.click('#logout');await waitText(page,'#status','You are signed out');
 const finished=page.waitForResponse(response=>response.url().endsWith('/api/company/resources/start'));release();await (await finished).finished();await page.waitForLoadState('networkidle');
 assert.equal(page.url(),origin+'/company/booking-control');assert.equal(await page.locator('#google-status').textContent(),'');
}));

test('company pending setting survives failure to remove its browser record',{skip:!available},()=>companyFixture(async(page,state)=>{
 await business(page);await page.evaluate(()=>{Storage.prototype.removeItem=()=>{throw new Error('Synthetic storage refusal');};});
 await submit(page);await waitText(page,'#business-status','could not safely save');
 const first=state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body;
 await page.click('#save-business');await waitText(page,'#business-status','could not safely save');
 assert.deepEqual(state.calls.filter(c=>c.path==='/api/company/settings'&&c.body).at(-1).body,first);
}));

test('company record checks distinguish enquiry copies, busy work and completed rechecks',{skip:!available},()=>companyFixture(async(page,state)=>{
 await section(page,'Google connections and record copies');
 const record={role:'agency',record_kind:'enquiry',record_id:id,reference:'Synthetic enquiry',sequence:'3',last_error_code:'unlisted',busy:true};
 state.handlers.set('/api/company/records/status',({reply})=>reply({records:[record],total:51,limited:true}));
 await page.click('#record-refresh');await waitText(page,'#record-status','first 50');await waitText(page,'#record-list','Enquiry Synthetic enquiry');
 assert.equal(await page.getByRole('button',{name:'A check is running',exact:true}).isDisabled(),true);
 record.busy=false;await page.click('#record-refresh');await waitText(page,'#record-list','Check this record again');
 state.handlers.set('/api/company/records/recheck',({reply})=>{state.handlers.set('/api/company/records/status',({reply})=>reply({records:[],total:0,limited:false}));reply({code:'already_checked'});});
 await page.getByRole('button',{name:'Check this record again',exact:true}).click();await waitText(page,'#record-status','No spreadsheet update problems');
 state.handlers.set('/api/company/records/status',({reply})=>reply({},503));await page.click('#record-refresh');await waitText(page,'#record-status','could not be checked');
}));

test('company current mode resolves the matching saved reference after a lost acknowledgement',{skip:!available},()=>companyFixture(async(page,state)=>{
 state.handlers.set('/api/company/control/change',({body,reply})=>{state.saved=body;reply({},503);});
 await page.click('#change');await waitText(page,'#status','response was interrupted');
 state.handlers.set('/api/company/control/status',({reply})=>reply({snapshot:{...state.snapshot,enabled:true},csrf_token:'a'.repeat(64),progress:'effective',operation_id:state.saved.operation_id}));
 await page.click('#refresh');await waitText(page,'#status','Booking is on');
 assert.equal(await page.evaluate(()=>window.PracticeCompanyCommands.read('mode')),null);
 await page.evaluate(()=>{Storage.prototype.getItem=()=>{throw new Error('Synthetic storage refusal');};});
 await page.click('#refresh');await waitText(page,'#status','could not safely save');assert.equal(await page.locator('#change').isDisabled(),true);
 await business(page);await waitText(page,'#business-status','could not safely save');assert.equal(await page.locator('#save-business').isDisabled(),true);
}));

test('company Google approval uses only the documented destination and reloads a consent return',{skip:!available},()=>companyFixture(async(page,state,origin)=>{
 await page.goto(origin+'/company/booking-control#google-consent='+id+'.pending');await page.reload();await page.locator('#signed-in').waitFor({state:'visible'});await page.waitForLoadState('networkidle');
 assert.equal(new URL(page.url()).hash,'');assert.ok(state.calls.some(c=>c.path==='/api/company/resources/status'));
 await section(page,'Google connections and record copies');state.handlers.set('/api/company/resources/start',({reply})=>reply({authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic'}));
 await page.route('https://accounts.google.com/**',route=>route.fulfill({status:200,contentType:'text/html',body:'<p>Synthetic approval destination</p>'}));
 await page.locator('[data-google-resource="calendar"]').click();await page.waitForURL('https://accounts.google.com/**');
 assert.equal(new URL(page.url()).searchParams.get('client_id'),'synthetic');
}));
