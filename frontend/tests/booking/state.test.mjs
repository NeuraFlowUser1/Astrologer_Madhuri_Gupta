import test from 'node:test';
import assert from 'node:assert/strict';
import {reducer} from '../../src/booking/state.mjs';
const slot={starts_at:'2030-01-01T10:00:00+05:30'};
const draft={service:'kundli-prediction',day:'2030-01-01',slot,details:{email:'test@example.invalid'},credential:{request_id:'saved'},phase:'checking',ack:true};
test('proven rejection preserves entered details and selection, but requires fresh agreement',()=>{
 const state=reducer(draft,{type:'rejected',message:'Payment setup is incomplete'});
 assert.equal(state.credential,null);assert.equal(state.slot,slot);assert.equal(state.details,draft.details);assert.equal(state.ack,false);
 const loading=reducer(state,{type:'slots-loading'});assert.equal(loading.slot,slot);
 assert.equal(reducer(loading,{type:'slots',service:state.service,day:state.day,value:{slots:[slot]}}).slot,slot);
 assert.equal(reducer(loading,{type:'slots',service:state.service,day:state.day,value:{slots:[]}}).slot,null);
});
test('service links cannot replace a saved unresolved attempt',()=>{
 assert.equal(reducer(draft,{type:'edit',name:'service',value:'numerology'}),draft);
 const state=reducer({...draft,credential:null},{type:'edit',name:'service',value:'numerology'});
 assert.equal(state.service,'numerology');assert.equal(state.slot,null);
});
