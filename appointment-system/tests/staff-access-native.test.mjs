import {test} from 'node:test';
import assert from 'node:assert/strict';
import {staffFixture,available,id,waitText,within} from './staff-page-fixture.mjs';

// Authentication failures must be handled before attempting to read a reply.
// A proxy can replace an expired-session reply with HTML or broken JSON.
for(const [path,trigger] of [
 ['/api/studio/calendar/list',page=>page.locator('#calendar-view button').click()],
 ['/api/studio/calendar/month',page=>page.click('#calendar-next')],
 ['/api/studio/appointments/detail',page=>page.evaluate(id=>document.dispatchEvent(new CustomEvent('studio-appointment',{detail:id})),id)],
 ['/api/studio/inbox/list',page=>page.click('#inbox-refresh')],
 ['/api/studio/resources/start',page=>page.click('#connect')],
])for(const status of [401,403])test(`${path} clears every private staff panel after ${status}, even without a readable reply`,{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set(path,({res})=>{res.writeHead(status,{'content-type':status===401?'text/html':'application/json'});res.end(status===401?'<h1>Sign in</h1>':'{broken');});
 await trigger(page);await waitText(page,'#status','Sign in again');
 assert.equal(await page.locator('#connection-panel').isVisible(),false);
 assert.equal(await page.locator('#calendar-panel').isVisible(),false);
 assert.equal(await page.locator('#inbox-panel').isVisible(),false);
 assert.equal(await page.locator('#account').textContent(),'');
 assert.equal(await page.locator('#calendar-month button').count(),0);
 assert.equal(await page.locator('#calendar-items li').count(),0);
 assert.equal(await page.locator('#signin-panel').isVisible(),true);
 assert.equal(await page.locator('[data-role]').first().isDisabled(),false);
}));

test('late calendar reply cannot restore private data after another staff request loses permission',{skip:!available},()=>staffFixture(async(page,state)=>{
 const calendar=Promise.withResolvers(),inbox=Promise.withResolvers();
 state.handlers.set('/api/studio/calendar/list',({body,reply})=>{calendar.resolve(()=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[{id,kind:'closure',reason:'Private synthetic reason',starts_at:'2031-04-04T10:30:00Z',ends_at:'2031-04-04T10:50:00Z'}],next_cursor:null}));});
 state.handlers.set('/api/studio/inbox/list',({res})=>{inbox.resolve(()=>{res.writeHead(403,{'content-type':'text/html'});res.end('Permission expired');});});
 // The inbox request can already be in flight when calendar work starts.
 await page.evaluate(()=>{document.querySelector('#inbox-refresh').click();document.querySelector('#calendar-view').requestSubmit();});
 const [finish,deny]=await within(Promise.all([calendar.promise,inbox.promise]));deny();
 await waitText(page,'#status','Sign in again');finish();
 await page.waitForTimeout(50);assert.equal(await page.locator('#calendar-items li').count(),0);
 assert.equal(await page.locator('#calendar-panel').isVisible(),false);
}));
