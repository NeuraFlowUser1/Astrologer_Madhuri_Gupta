import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createStateController,publicDisplaySnapshot,admissionAllowed,displayAllowed} from '../browser/product-state.mjs';
import {createReactBindings} from '../browser/react-bindings.mjs';

const epoch='891d05ec-8ab2-4a87-b537-1c30f2b694b6';
const reply=enabled=>Response.json({enabled,activation_epoch:epoch});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function timerClock(){
 let now=0,next=0;const timers=new Map();
 return {clock:()=>now,setTimer:(fn,delay)=>{const id=++next;timers.set(id,{at:now+delay,fn});return id;},clearTimer:id=>timers.delete(id),
  count:()=>timers.size,async advance(ms){const end=now+ms;let turns=0;
   while(true){const first=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!first)break;
    assert.ok(++turns<1000,'timer must not spin');now=first[1].at;timers.delete(first[0]);first[1].fn();await flush();}
   now=end;await flush();}};
}
function environment(){const win=new EventTarget(),doc=new EventTarget();doc.visibilityState='visible';return {win,doc};}

test('one visible public hour makes sixty periodic reads, and active work retains five-second checks',async()=>{
 const time=timerClock(),{win,doc}=environment();let calls=0;
 const store=createStateController({...time,fetcher:async()=>{calls++;return reply(true);}});
 const stop=store.start(win,doc,{profile:'public'});await flush();assert.equal(calls,1);
 await time.advance(3600000);assert.equal(calls,61);assert.equal(time.count(),1);
 store.setProfile('active');await flush();assert.equal(calls,62);
 await time.advance(15000);assert.equal(calls,65);assert.equal(time.count(),1);
 stop();assert.equal(time.count(),0);await time.advance(120000);assert.equal(calls,65);
});

test('completed bootstrap read is reused, profile changes use last attempt and duplicate starts do not add owners',async()=>{
 const time=timerClock(),{win,doc}=environment();let calls=0;
 const store=createStateController({...time,fetcher:async()=>{calls++;return reply(true);}});
 await store.refresh({force:true});const stop=store.start(win,doc,{profile:'public',refreshOnStart:false});
 assert.equal(store.start(win,doc,{profile:'active'}),stop);await flush();assert.equal(calls,1);
 await time.advance(60000);assert.equal(calls,2);
 store.setProfile('active');await flush();assert.equal(calls,3);
 await time.advance(3000);store.setProfile('public');await time.advance(56999);assert.equal(calls,3);
 await time.advance(1);assert.equal(calls,4);stop();
 assert.throws(()=>store.setProfile('unknown'));assert.throws(()=>store.start(win,doc,{profile:'unknown'}));
});

test('hidden/page-hidden time has no periodic work; foreground events share freshness; old cleanup cannot stop a restart',async()=>{
 const time=timerClock(),{win,doc}=environment();let calls=0;
 const store=createStateController({...time,fetcher:async()=>{calls++;return reply(true);}});
 const first=store.start(win,doc,{profile:'public'});await flush();
 doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(time.count(),0);
 await time.advance(3600000);assert.equal(calls,1);
 doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));
 win.dispatchEvent(new Event('pageshow'));win.dispatchEvent(new Event('focus'));await flush();assert.equal(calls,2);
 win.dispatchEvent(new Event('pagehide'));assert.equal(time.count(),0);assert.equal(admissionAllowed(store.getSnapshot()),false);
 await time.advance(120000);assert.equal(calls,2);
 win.dispatchEvent(new Event('pageshow'));await flush();assert.equal(calls,3);
 first();const second=store.start(win,doc,{profile:'public'});await flush();const before=calls;
 first();await time.advance(60000);assert.equal(calls,before+1);second();assert.equal(time.count(),0);
});

test('in-flight periodic/focus/entry requests coalesce and a late ON cannot undo a newer OFF',async()=>{
 const time=timerClock(),{win,doc}=environment();let calls=0,release;
 const store=createStateController({...time,fetcher:()=>{calls++;return new Promise(resolve=>release=resolve);}});
 const stop=store.start(win,doc,{profile:'public'});await flush();
 const pending=store.refresh({force:true});win.dispatchEvent(new Event('focus'));store.setProfile('active');await flush();
 assert.equal(calls,1);assert.equal(store.refresh({force:true}),pending);
 const old=release;store.invalidate();const next=store.refresh({force:true});await flush();assert.equal(calls,2);
 release(reply(false));await next;old(reply(true));await pending;assert.equal(store.getSnapshot().enabled,false);
 stop();assert.equal(time.count(),0);
});

test('public display snapshots cannot admit a booking or share mutable server state',()=>{
 const on=publicDisplaySnapshot(true),off=publicDisplaySnapshot(false);
 assert.equal(displayAllowed(on),true);assert.equal(admissionAllowed(on),false);assert.equal(on.activation_epoch,null);
 assert.equal(admissionAllowed(off),false);assert.equal(Object.isFrozen(on),true);assert.throws(()=>publicDisplaySnapshot(1));
 let calls=0;const first=createStateController({serverSnapshot:()=>on,fetcher:()=>{calls++;}});
 const second=createStateController({serverSnapshot:()=>off});
 assert.equal(first.getServerSnapshot(),on);assert.equal(second.getServerSnapshot(),off);assert.equal(first.getSnapshot().enabled,false);
 assert.equal(calls,0);assert.throws(()=>createStateController({serverSnapshot:true}));
 const hydrated=createStateController({serverSnapshot:()=>({...on,verified:true,activation_epoch:epoch}),initialDisplay:true});
 assert.equal(displayAllowed(hydrated.getSnapshot()),true);assert.equal(admissionAllowed(hydrated.getSnapshot()),false);
 assert.equal(hydrated.getSnapshot().activation_epoch,null);assert.throws(()=>createStateController({initialDisplay:1}));
});

function bindingHarness(){
 const effects=[],contexts=[];let contextStore=null,location={pathname:'/',search:''},navigations=[];
 const React={createContext:()=>{const c={Provider:'Provider'};contexts.push(c);return c;},useContext:()=>contextStore,
  createElement:(type,props,...children)=>({type,props,children}),useRef:value=>({current:value}),
  useEffect:fn=>effects.push(fn),useSyncExternalStore:(_,get)=>get(),Fragment:'Fragment'};
 const Router={Link:'Link',useLocation:()=>location,useNavigate:()=>to=>navigations.push(to)};
 return {React,Router,effects,navigations,setStore:value=>{contextStore=value;},setLocation:value=>{location=value;}};
}
const click=(extra={})=>({button:0,preventDefault(){this.defaultPrevented=true;},stopPropagation(){},...extra});

test('entry waits for one fresh result; OFF/failure cannot execute an action and explicit fallback is retained',async()=>{
 const harness=bindingHarness();let current={enabled:true,verified:true,checking:false},release,calls=0,actions=0;
 const store={getSnapshot:()=>current,getServerSnapshot:()=>current,subscribe:()=>()=>{},setProfile:()=>{},start:()=>()=>{},
  refresh:()=>{calls++;return new Promise(resolve=>release=resolve);}};
 const ui=createReactBindings(harness.React,harness.Router,{surfaces:[],state:store,lifecycleOwner:'entry'});
 const link=ui.BookingLink({to:'/booking?service=numerology',children:'Book'});
 const a=click();link.props.onClick(a);link.props.onClick(click());await flush();assert.equal(calls,1);assert.deepEqual(harness.navigations,[]);
 release();await flush();assert.deepEqual(harness.navigations,['/booking?service=numerology']);assert.equal(a.defaultPrevented,true);
 const button=ui.BookingButton({offPath:'/phone',onClick:()=>actions++});button.props.onClick(click());await flush();
 current={enabled:false,verified:true,checking:false};release();await flush();assert.equal(actions,0);assert.equal(harness.navigations.at(-1),'/phone');
});

test('another booking intent supersedes a slow one; modified links retain native navigation',async()=>{
 const harness=bindingHarness();let current={enabled:true,verified:true,checking:false},release,calls=0;
 const store={getSnapshot:()=>current,getServerSnapshot:()=>current,subscribe:()=>()=>{},setProfile:()=>{},start:()=>()=>{},
  refresh:()=>{calls++;return new Promise(resolve=>release=resolve);}};
 const ui=createReactBindings(harness.React,harness.Router,{surfaces:[],state:store,lifecycleOwner:'entry'});
 const old=ui.BookingLink({to:'/booking?service=vedic-astrology'});const next=ui.BookingLink({to:'/booking?service=numerology'});
 old.props.onClick(click());await flush();const first=release;
 next.props.onClick(click());await flush();const second=release;
 first();await flush();assert.deepEqual(harness.navigations,[]);second();await flush();assert.deepEqual(harness.navigations,['/booking?service=numerology']);
 for(const attributes of [{target:'_blank'},{download:''},{}]){
  const link=ui.BookingAnchor({href:'/booking',...attributes});const event=click(attributes.target||Object.hasOwn(attributes,'download')?{}:{ctrlKey:true});
  link.props.onClick(event);assert.equal(event.defaultPrevented,undefined);
 }
 assert.equal(calls,2);
});

test('per-render context is used by copy and entry and does not overwrite the default store',async()=>{
 const h=bindingHarness();let defaultReads=0,contextReads=0;
 const off={getSnapshot:()=>publicDisplaySnapshot(false),getServerSnapshot:()=>publicDisplaySnapshot(false),subscribe:()=>()=>{},
  setProfile:()=>{},start:()=>()=>{},refresh:async()=>defaultReads++};
 const on={...off,getSnapshot:()=>({enabled:true,verified:true,checking:false}),refresh:async()=>contextReads++};
 const ui=createReactBindings(h.React,h.Router,{surfaces:[],state:off,lifecycleOwner:'entry'});
 h.setStore(on);assert.equal(ui.BookingOnly({children:'on'}),'on');
 ui.BookingLink({to:'/booking'}).props.onClick(click());await flush();assert.equal(contextReads,1);assert.equal(defaultReads,0);
 h.setStore(null);assert.equal(ui.BookingOnly({children:'off'}),null);
 assert.equal(ui.BookingStateProvider({controller:on,children:'x'}).props.value,on);
 assert.throws(()=>ui.BookingStateProvider({controller:null}));
 assert.throws(()=>createReactBindings(h.React,h.Router,{lifecycleOwner:'unknown'}));
});

test('initial native pageshow reuses bootstrap; restored and initially hidden pages refresh',async()=>{
 const time=timerClock(),{win,doc}=environment();let calls=0;
 const store=createStateController({...time,fetcher:async()=>{calls++;return reply(true);}});
 const show=persisted=>Object.assign(new Event('pageshow'),{persisted});
 const stop=store.start(win,doc,{profile:'public'});await flush();assert.equal(calls,1);
 await time.advance(97);win.dispatchEvent(show(false));await flush();assert.equal(calls,1);
 assert.equal(admissionAllowed(store.getSnapshot()),true);
 win.dispatchEvent(new Event('pagehide'));assert.equal(admissionAllowed(store.getSnapshot()),false);
 win.dispatchEvent(show(true));await flush();assert.equal(calls,2);stop();
 const hidden=environment();hidden.doc.visibilityState='hidden';let hiddenCalls=0;
 const waiting=createStateController({...time,fetcher:async()=>{hiddenCalls++;return reply(true);}});
 const end=waiting.start(hidden.win,hidden.doc,{profile:'public'});await flush();assert.equal(hiddenCalls,0);
 hidden.doc.visibilityState='visible';hidden.win.dispatchEvent(show(false));await flush();assert.equal(hiddenCalls,1);
 end();assert.equal(time.count(),0);
});
