import test from 'node:test';
import assert from 'node:assert/strict';
import {legacyDestination,migrateLegacyLocation} from '../src/site/routes.mjs';
test('legacy booking preserves only a known service and safe section',()=>{
 assert.equal(legacyDestination('#/booking?service=numerology&secret=private#details'),'/booking?service=numerology#details');
 assert.equal(legacyDestination('#/booking?service=unknown'),'/booking');
});
test('private, external and unknown routes cannot become redirects',()=>{
 for(const input of ['#//example.com','#/studio','#/api/callback?code=private','#/unknown','#approach','#/\\example.com','#/%2fexample.com'])assert.equal(legacyDestination(input),null,input);
});
test('known legacy route uses replacement and preserves existing history state',()=>{
 let call;const history={state:{key:'existing'},replaceState:(...args)=>call=args};
 migrateLegacyLocation({pathname:'/',hash:'#/about#approach'},history);
 assert.deepEqual(call,[history.state,'','/about#approach']);
 call=null;migrateLegacyLocation({pathname:'/studio',hash:'#/about'},history);assert.equal(call,null);
});
test('malformed inputs and private fragments never become a destination',()=>{
 for(const input of [undefined,null,0,{},[], '#/\\[invalid'])assert.equal(legacyDestination(input),null);
 assert.equal(legacyDestination('#/contact?email=private&token=private#access_secret'),'/contact');
 assert.equal(legacyDestination('#/booking?service=numerology&receipt=private#section-2'),'/booking?service=numerology#section-2');
});
test('an unrecognized root fragment does not rewrite browsing history',()=>{
 let calls=0;
 migrateLegacyLocation({pathname:'/',hash:'#access=private'}, {state:null,replaceState:()=>calls++});
 assert.equal(calls,0);
});
