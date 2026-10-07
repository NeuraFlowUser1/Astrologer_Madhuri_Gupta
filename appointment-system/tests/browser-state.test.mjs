import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createStateController,checkedDisplay,displayAllowed,admissionAllowed,retainView} from '../browser/product-state.mjs';
import {createReactBindings} from '../browser/react-bindings.mjs';
const epoch='891d05ec-8ab2-4a87-b537-1c30f2b694b6';
const state=enabled=>({enabled,activation_epoch:epoch});
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('only the minimal current state contract is accepted',()=>{
 assert.deepEqual(checkedDisplay(state(true)),{...state(true),verified:true});
 for(const value of [null,[],{},state(1),{...state(true),extra:1},{...state(true),activation_epoch:null},
  {...state(true),activation_epoch:'00000000-0000-0000-0000-000000000000'}])assert.throws(()=>checkedDisplay(value));
});

test('OFF before first check, bounded polling, one request and no positive persistence',async()=>{
 let calls=0,now=1,enabled=true;
 const store=createStateController({clock:()=>now,fetcher:async(url,options)=>{
  ++calls;assert.equal(url,'/api/service-state');assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
  return Response.json(state(enabled));}});
 assert.equal(store.getSnapshot().enabled,false);assert.equal(store.getServerSnapshot(),store.getServerSnapshot());
 let notices=0;const unsubscribe=store.subscribe(()=>notices++);
 const pending=store.refresh();assert.equal(store.refresh(),pending);await pending;
 assert.equal(store.getSnapshot().enabled,true);await store.refresh();assert.equal(calls,1);
 now+=5000;enabled=false;await store.refresh();assert.equal(store.getSnapshot().enabled,false);assert.equal(notices,4);
 unsubscribe();store.invalidate();assert.equal(notices,4);
});

test('an old ON response cannot revive a page after invalidation or a newer OFF check',async()=>{
 let release;let calls=0;
 const store=createStateController({fetcher:()=>++calls===1?new Promise(resolve=>release=resolve):Promise.resolve(Response.json(state(false)))});
 const old=store.refresh();await tick();store.invalidate();await store.refresh({force:true});release(Response.json(state(true)));await old;
 assert.equal(store.getSnapshot().enabled,false);assert.equal(store.getSnapshot().verified,true);
});

test('HTTP, response shape, Unicode and size failures remove retained ON immediately',async()=>{
 let reply=Response.json(state(true));const store=createStateController({fetcher:async()=>reply});
 await store.refresh();assert.equal(store.getSnapshot().enabled,true);
 for(const invalid of [new Response('not JSON'),Response.json({enabled:true}),new Response('{}',{status:500}),
  new Response(' '.repeat(1025),{headers:{'Content-Type':'application/json'}}),
  new Response(Uint8Array.of(0xff),{headers:{'Content-Type':'application/json'}})]){
  reply=invalid;await store.refresh({force:true});assert.equal(store.getSnapshot().enabled,false);assert.equal(store.getSnapshot().verified,false);
 }
});

test('foreground checks coalesce, preserve a visible form and pause without disposing it',async()=>{
 const windowObject=new EventTarget(),documentObject=new EventTarget();documentObject.visibilityState='visible';
 let calls=0,release,now=0;const store=createStateController({clock:()=>now,fetcher:()=>{++calls;return new Promise(resolve=>release=resolve);}});
 const stop=store.start(windowObject,documentObject);assert.equal(store.start(windowObject,documentObject),stop);
 await tick();release(Response.json(state(true)));await tick();assert.equal(admissionAllowed(store.getSnapshot()),true);
 now=200;windowObject.dispatchEvent(new Event('focus'));windowObject.dispatchEvent(new Event('pageshow'));
 documentObject.dispatchEvent(new Event('visibilitychange'));await tick();
 assert.equal(calls,2);assert.equal(store.getSnapshot().foreground_revision,1);
 assert.equal(displayAllowed(store.getSnapshot()),true);assert.equal(admissionAllowed(store.getSnapshot()),false);
 assert.equal(retainView(store.getSnapshot()),true);release(Response.json(state(true)));await tick();
 documentObject.visibilityState='hidden';documentObject.dispatchEvent(new Event('visibilitychange'));
 assert.equal(store.getSnapshot().enabled,true);assert.equal(calls,2);
 windowObject.dispatchEvent(new Event('pagehide'));assert.equal(displayAllowed(store.getSnapshot()),false);assert.equal(retainView(store.getSnapshot()),true);
 documentObject.visibilityState='visible';documentObject.dispatchEvent(new Event('visibilitychange'));await tick();assert.equal(calls,3);
 release(Response.json(state(false)));await tick();assert.equal(retainView(store.getSnapshot()),false);
 stop();windowObject.dispatchEvent(new Event('focus'));assert.equal(calls,3);assert.equal(store.getSnapshot().enabled,false);
});

test('unresponsive display service times out and explicit invalidation resolves the pending check',async()=>{
 const store=createStateController({fetcher:()=>new Promise(()=>{})});
 const start=Date.now();await store.refresh();assert.equal(store.getSnapshot().enabled,false);assert.ok(Date.now()-start<4000);
 const pending=store.refresh({force:true});store.invalidate();await pending;
});

test('shared React bindings have no saved receipt exception and clicks use current state',()=>{
 let current={enabled:false},navigation,clicks=0,hooks=0;
 const store={getSnapshot:()=>current,getServerSnapshot:()=>current,subscribe:()=>()=>{},start:()=>()=>{},refresh:async()=>{}};
 const React={createElement:(type,props,...children)=>({type,props,children}),useEffect:()=>{},useRef:()=>({current:false}),Fragment:'Fragment',
  useSyncExternalStore:(_subscribe,get)=>{++hooks;return get();}};
 const Router={Link:'Link',useLocation:()=>({pathname:'/'}),useNavigate:()=>value=>navigation=value};
 const ui=createReactBindings(React,Router,{surfaces:[{path:'/booking-policy',class:'booking'}],state:store});
 assert.equal(ui.BookingOnly({children:'booking'}),null);assert.equal(ui.BookingCopy({children:'online',off:'call'}),'call');
 assert.equal(ui.BookingLink({to:'/booking',children:'Book',bookingMode:'hide'}),null);
 assert.equal(ui.BookingLink({to:'/booking/receipt',children:'Receipt'}).props.to,'/contact');
 assert.equal(ui.BookingAnchor({href:'/BOOKING.html',children:'Book'}).props.href,'/contact');
 assert.equal(ui.BookingAnchor({href:'/booking',bookingMode:'hide'}),null);
 assert.equal(ui.BookingLink({to:'/about',children:'About'}).props.to,'/about');assert.equal(hooks,7);
 assert.equal(ui.BookingRoute({children:'receipt',readSavedReceipt:()=>{throw Error('must never read a saved receipt');}}).children[1].type,ui.UnavailablePage);
 current={enabled:true,verified:true,checking:false,activation_epoch:epoch,retained_on_epoch:epoch};const button=ui.BookingButton({children:'Book',onClick:()=>clicks++});
 current={enabled:false};button.props.onClick({preventDefault(){},stopPropagation(){}});assert.equal(navigation,'/contact');assert.equal(clicks,0);
 assert.equal(ui.BookingButton({bookingMode:'hide'}),null);
 current={enabled:true,verified:true,checking:false,activation_epoch:epoch,retained_on_epoch:epoch};button.props.onClick({});assert.equal(clicks,1);assert.equal(ui.BookingRoute({children:'booking'}).children[0].children[0],'booking');
 assert.equal(ui.BookingNavigationLink({to:'/booking'}).props.bookingMode,'hide');
 assert.equal(ui.UnavailablePage().children[0].children[0],'Page not found');ui.ProductNavigationCheck();
});

test('React visibility preserves ordinary destinations and uses explicit contact alternatives when OFF',()=>{
 let current={enabled:false},started=0,refreshed=0,navigated;const effects=[];
 const store={getSnapshot:()=>current,getServerSnapshot:()=>current,subscribe:()=>()=>{},start:()=>{started++;return()=>{};},refresh:async()=>{refreshed++;}};
 const React={createElement:(type,props,...children)=>({type,props,children}),useEffect:fn=>effects.push(fn),useRef:()=>({current:false}),Fragment:'Fragment',useSyncExternalStore:(_,get)=>get()};
 const ui=createReactBindings(React,{Link:'Link',useLocation:()=>({pathname:'/booking'}),useNavigate:()=>value=>navigated=value},{surfaces:[],state:store});
 for(const target of [null,{},'relative','//other.test/path','https://other.test/path','/%E0%A4%A'])assert.equal(ui.BookingAnchor({href:target,children:'Original'}).props.href,target);
 const off=ui.BookingButton({children:'Book',offText:'Call us',offPath:'/phone'});assert.equal(off.children[0],'Call us');off.props.onClick({preventDefault(){},stopPropagation(){}});assert.equal(navigated,'/phone');
 current={enabled:true,verified:true,checking:false,activation_epoch:epoch,retained_on_epoch:epoch};assert.equal(ui.BookingOnly({children:'Booking'}),'Booking');assert.equal(ui.BookingCopy({children:'Online',off:'Call'}),'Online');assert.equal(ui.BookingAnchor({href:'/booking',children:'Book'}).props.href,'/booking');ui.BookingButton({}).props.onClick({});
 ui.ProductNavigationCheck();for(const effect of effects)effect();assert.equal(started,1);assert.equal(refreshed,1);
});
