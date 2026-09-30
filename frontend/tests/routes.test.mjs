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
