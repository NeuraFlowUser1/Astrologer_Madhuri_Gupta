import {test} from 'node:test';
import assert from 'node:assert/strict';
import {staffFixture,available,id,other,waitText} from './staff-page-fixture.mjs';
const item=(category='enquiry')=>({item_key:(category==='enquiry'?'enquiry':category==='payment'?'payment':'delivery')+':'+id,category,review_revision:2,state:'attention',created_at:'2031-04-04T10:30:00Z',subject:'Synthetic subject',reference:id,reviews:[],...(category==='enquiry'?{enquiry:{name:'Fixture Person',email:'fixture@example.test',phone:'',subject:'Synthetic subject',message:'<script>window.unwanted=true</script>'}}:{})});
async function show(page,state,row){
 state.handlers.set('/api/studio/inbox/list',({body,reply})=>reply({code:'ok',view:body.view,items:[row],next_cursor:null}));
 state.handlers.set('/api/studio/inbox/detail',({reply})=>reply({code:'ok',item:row}));
 await page.click('#inbox-refresh');await page.locator('#inbox-items button').click();await page.locator('#inbox-detail').waitFor();
}
test('staff reads escaped enquiry details, records a note, and keeps all private content out of browser storage',{skip:!available},()=>staffFixture(async(page,state)=>{
 const row=item();await show(page,state,row);assert.match(await page.locator('#inbox-content').textContent(),/<script>/);assert.equal(await page.evaluate(()=>window.unwanted),undefined);
 assert.equal(await page.locator('#inbox-action-retry').isVisible(),false);assert.equal(await page.locator('#inbox-action-refund').isVisible(),false);
 await page.fill('#review-note','x');await page.locator('#inbox-review').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));await waitText(page,'#inbox-review-status','short single-line');
 state.handlers.set('/api/studio/inbox/review',({body,reply})=>{row.review_revision++;row.reviews=[{note:body.note,created_at:row.created_at,role:'client'}];reply({code:'review_saved',revision:3});});
 await page.fill('#review-note','Synthetic follow-up completed');await page.getByRole('button',{name:'Save review note',exact:true}).click();await waitText(page,'#inbox-review-status','Review note saved');
 assert.match(await page.locator('#inbox-reviews').textContent(),/Synthetic follow-up completed/);const sent=state.calls.find(x=>x.path.endsWith('/inbox/review'));assert.equal(sent.body.expected_revision,2);assert.equal(sent.body.item_key,row.item_key);
 assert.equal(await page.evaluate(()=>JSON.stringify(localStorage).includes('Synthetic follow-up')),false);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),0);
}));
test('payment reviews only close with recorded outcomes and never issue a payment or refund',{skip:!available},()=>staffFixture(async(page,state)=>{
 const row=item('payment');row.financial_resource_id=other;row.financial_resources=[{id:other,kind:'dispute',status:'open',verified:false,amount_paise:100}];await show(page,state,row);
 assert.equal(await page.locator('#inbox-action-refund').isVisible(),false);assert.equal(await page.locator('#inbox-action-retry').textContent(),'Check payment again');
 row.financial_resources[0]={id:other,kind:'dispute',status:'won',verified:true,amount_paise:100,outcome:'won',respond_by:1933068600};await show(page,state,row);
 assert.equal(await page.locator('#inbox-action-refund').textContent(),'Finish dispute review');
 await page.click('#inbox-action-refund');await waitText(page,'#inbox-review-status','First write');
 state.handlers.set('/api/studio/inbox/resource-reviewed',({reply})=>reply({code:'resource_reviewed',revision:3}));await page.fill('#review-note','Verified provider outcome');await page.click('#inbox-action-refund');await waitText(page,'#inbox-status','did not send money');
 row.financial_resources=[{id:other,kind:'refund',status:'processed',verified:true,amount_paise:100}];await show(page,state,row);
 state.handlers.set('/api/studio/inbox/refund-verified',({reply})=>reply({code:'refund_verified',revision:3}));await page.fill('#review-note','Verified full refund');await page.click('#inbox-action-refund');await waitText(page,'#inbox-status','did not send money');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/resource-reviewed')).length,1);assert.equal(state.calls.filter(x=>x.path.endsWith('/refund-verified')).length,1);
}));
test('delivery retry preserves work identity and reports queued rather than delivered',{skip:!available},()=>staffFixture(async(page,state)=>{
 const row=item('meeting');await show(page,state,row);await page.click('#inbox-action-retry');await waitText(page,'#inbox-review-status','First write');
 state.handlers.set('/api/studio/inbox/retry',({reply})=>reply({code:'retry_queued',revision:3}));await page.fill('#review-note','Connection checked');await page.click('#inbox-action-retry');await waitText(page,'#inbox-status','does not confirm delivery');
 const sent=state.calls.find(x=>x.path.endsWith('/inbox/retry'));assert.equal(sent.body.item_key,row.item_key);assert.equal(sent.body.expected_revision,2);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),0);
}));
test('uncertain staff review survives reload, rejects a mismatched answer, and only reads its original saved result',{skip:!available},()=>staffFixture(async(page,state)=>{
 await show(page,state,item());let operation;
 state.handlers.set('/api/studio/inbox/review',({body,reply})=>{operation=body.operation_id;reply({code:'uncertain'},503);});
 await page.fill('#review-note','Private fixture note');await page.getByRole('button',{name:'Save review note',exact:true}).click();await waitText(page,'#inbox-review-status','could not confirm');
 await page.reload();await page.locator('#inbox-retry-review').waitFor();state.handlers.set('/api/studio/inbox/action-result',({reply})=>reply({code:'review_saved',operation_id:other}));
 await page.click('#inbox-retry-review');await waitText(page,'#inbox-review-status','could not confirm');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),1);
 state.handlers.set('/api/studio/inbox/action-result',({body,reply})=>reply({code:'review_saved',operation_id:body.operation_id}));await page.click('#inbox-retry-review');await waitText(page,'#inbox-status','Earlier actions checked');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/inbox/review')).length,1);assert.ok(state.calls.filter(x=>x.path.endsWith('/action-result')).every(x=>x.body.operation_id===operation));
 assert.equal(await page.evaluate(()=>JSON.stringify(localStorage).includes('Private fixture note')),false);
}));
test('definitive stale review refusal clears only the rejected action and blocked storage prevents any write',{skip:!available},()=>staffFixture(async(page,state)=>{
 await show(page,state,item());state.handlers.set('/api/studio/inbox/review',({reply})=>reply({code:'revision_changed'},409));
 await page.fill('#review-note','Checked the customer question');await page.getByRole('button',{name:'Save review note',exact:true}).click();await waitText(page,'#inbox-review-status','Another review was saved first');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),0);
 await show(page,state,item());await page.fill('#review-note','A second private note');await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw Error('Synthetic storage refusal');};});
 await page.getByRole('button',{name:'Save review note',exact:true}).click();await waitText(page,'#inbox-review-status','could not safely save');assert.equal(state.calls.filter(x=>x.path.endsWith('/inbox/review')).length,1);
}));
test('inbox rejects malformed, oversize and unauthorized responses without keeping stale private details',{skip:!available},()=>staffFixture(async(page,state)=>{
 await show(page,state,item());
 for(const invalid of [{code:'ok',view:'wrong',items:[],next_cursor:null},{code:'ok',view:'enquiries',items:Array(51).fill(item()),next_cursor:null},{code:'ok',view:'enquiries',items:[{...item(),review_revision:-1}],next_cursor:null},{code:'ok',view:'enquiries',items:[],next_cursor:'bad'}]){
  state.handlers.set('/api/studio/inbox/list',({reply})=>reply(invalid));await page.click('#inbox-refresh');await waitText(page,'#inbox-status','could not confirm');assert.equal(await page.locator('#inbox-items li').count(),0);
 }
 state.handlers.set('/api/studio/inbox/list',({res})=>{res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({padding:'x'.repeat(66000)}));});await page.click('#inbox-refresh');await waitText(page,'#inbox-status','could not confirm');
 state.handlers.set('/api/studio/inbox/list',({reply})=>reply({code:'access_unavailable'},403));await page.click('#inbox-refresh');await waitText(page,'#status','Sign in again');assert.equal(await page.locator('#inbox-panel').isVisible(),false);assert.equal(await page.locator('#inbox-content').textContent(),'');
}));
test('inbox rejects mismatched details and unverified resource shapes before showing action controls',{skip:!available},()=>staffFixture(async(page,state)=>{
 for(const row of [{...item(),item_key:'enquiry:'+other},{...item(),enquiry:{name:1}}, {...item('payment'),financial_resources:[{kind:'refund',status:'processed',verified:'yes',amount_paise:100}]}, {...item('payment'),financial_resource_id:other,financial_resources:[]}, {...item(),reviews:[{note:23,created_at:'invalid'}]}]){
  state.handlers.set('/api/studio/inbox/list',({body,reply})=>reply({code:'ok',view:body.view,items:[item()],next_cursor:null}));
  state.handlers.set('/api/studio/inbox/detail',({reply})=>reply({code:'ok',item:row}));await page.click('#inbox-refresh');await page.locator('#inbox-items button').click();await waitText(page,'#inbox-status','could not confirm');assert.equal(await page.locator('#inbox-detail').isVisible(),false);
 }
}));
test('inbox pagination uses the returned cursor and view changes discard old rows',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set('/api/studio/inbox/list',({body,reply})=>reply({code:'ok',view:body.view,items:body.view==='issues'?[]:[{...item(),item_key:'enquiry:'+(body.after?other:id)}],next_cursor:body.after?null:'enquiry:'+id}));
 await page.click('#inbox-refresh');await page.locator('#inbox-more').waitFor();await page.click('#inbox-more');await page.waitForFunction(()=>document.querySelectorAll('#inbox-items li').length===2);
 assert.equal(state.calls.filter(x=>x.path.endsWith('/inbox/list')).at(-1).body.after,'enquiry:'+id);await page.click('#inbox-issues');await waitText(page,'#inbox-status','No recorded problems');assert.equal(await page.locator('#inbox-items li').count(),0);
 await page.click('#inbox-enquiries');await page.locator('#inbox-items button').waitFor();assert.equal(await page.locator('#inbox-enquiries').getAttribute('aria-pressed'),'true');
}));

test('agency inbox exposes only its record review and cannot display customer enquiries',{skip:!available},()=>staffFixture(async(page,state)=>{
 await page.evaluate(()=>document.dispatchEvent(new CustomEvent('studio-role',{detail:'agency'})));
 await waitText(page,'#inbox-purpose','NeuraFlow’s own record copies');await page.waitForFunction(()=>!document.querySelector('#inbox-refresh').disabled);
 assert.equal(await page.locator('#inbox-enquiries').isVisible(),false);
 const row={...item('agency_records'),reference:null,subject:null,review_revision:0,reviews:[{role:'agency',note:'Synthetic reviewed record',created_at:'2031-04-04T10:30:00Z'}]};
 await show(page,state,row);assert.equal(await page.getByRole('button',{name:'Open booking for support',exact:true}).count(),0);await waitText(page,'#inbox-reviews','Support');
 await page.fill('#review-note','Synthetic retry');state.handlers.set('/api/studio/inbox/retry',({reply})=>reply({code:'retry_unavailable'},409));await page.click('#inbox-action-retry');await waitText(page,'#inbox-review-status','cannot safely be retried');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),0);
 state.handlers.set('/api/studio/inbox/list',({body,reply})=>reply({code:'ok',view:body.view,items:[item()],next_cursor:null}));state.handlers.set('/api/studio/inbox/detail',({reply})=>reply({code:'ok',item:item()}));await page.click('#inbox-refresh');await page.locator('#inbox-items button').click();await waitText(page,'#inbox-status','could not confirm');assert.equal(await page.locator('#inbox-detail').isVisible(),false);
}));

test('inbox malformed financial evidence never exposes a refund action',{skip:!available},()=>staffFixture(async(page,state)=>{
 const base=item('payment');
 for(const resource of [null,{kind:'other'},{kind:'refund',status:1,verified:true,amount_paise:100},{kind:'refund',status:'processed',verified:true,amount_paise:-1}]){
  state.handlers.set('/api/studio/inbox/list',({body,reply})=>reply({code:'ok',view:body.view,items:[base],next_cursor:null}));state.handlers.set('/api/studio/inbox/detail',({reply})=>reply({code:'ok',item:{...base,financial_resources:[resource]}}));
  await page.click('#inbox-refresh');await page.locator('#inbox-items button').click();await waitText(page,'#inbox-status','could not confirm');assert.equal(await page.locator('#inbox-detail').isVisible(),false);
 }
 const row={...base,financial_resource_id:other,financial_resources:[{id:other,kind:'dispute',status:'won',verified:true,amount_paise:100,attention_reason:'evidence_changed'}]};await show(page,state,row);await waitText(page,'#inbox-content','Needs review');assert.equal(await page.locator('#inbox-action-refund').isVisible(),false);
}));

test('inbox wrong successful revision and non-JSON reply preserve the uncertain action',{skip:!available},()=>staffFixture(async(page,state)=>{
 await show(page,state,item());state.handlers.set('/api/studio/inbox/review',({reply})=>reply({code:'review_saved',revision:999}));await page.fill('#review-note','Synthetic reviewed enquiry');await page.getByRole('button',{name:'Save review note',exact:true}).click();await waitText(page,'#inbox-review-status','could not confirm');
 const saved=await page.evaluate(()=>window.PracticeStaffActions('inbox').get());assert.equal(saved.length,1);
 state.handlers.set('/api/studio/inbox/action-result',({res})=>{res.writeHead(502,{'content-type':'text/html'});res.end('<p>Synthetic gateway failure</p>');});await page.click('#inbox-retry-review');await page.waitForFunction(()=>!document.querySelector('#inbox-retry-review').disabled);await waitText(page,'#inbox-review-status','could not confirm');assert.deepEqual(await page.evaluate(()=>window.PracticeStaffActions('inbox').get()),saved);
 state.handlers.set('/api/studio/inbox/action-result',({reply})=>reply({code:'access_unavailable'},401));await page.click('#inbox-retry-review');await waitText(page,'#status','Sign in again');assert.equal(await page.locator('#inbox-content').textContent(),'');assert.deepEqual(await page.evaluate(()=>window.PracticeStaffActions('inbox').get()),saved);
}));

test('inbox time wait and refund refusal leave provider facts and money unchanged',{skip:!available},()=>staffFixture(async(page,state)=>{
 const row=item('payment');await show(page,state,row);await page.fill('#review-note','Synthetic provider evidence checked');
 state.handlers.set('/api/studio/inbox/retry',({reply})=>reply({code:'retry_wait'},429));await page.click('#inbox-action-retry');await waitText(page,'#inbox-review-status','Wait one minute');
 state.handlers.set('/api/studio/inbox/refund-verified',({reply})=>reply({code:'refund_not_verified'},409));await page.click('#inbox-action-refund');await waitText(page,'#inbox-review-status','full refund has not been verified');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('inbox').get().length),0);
 await page.fill('#review-note','bad\nnote');await page.click('#inbox-action-refund');await waitText(page,'#inbox-review-status','First write');
 assert.equal(state.calls.filter(c=>c.path.endsWith('/refund-verified')).length,1);
}));
