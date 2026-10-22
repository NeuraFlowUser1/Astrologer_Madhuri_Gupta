import {productState,displayAllowed} from './product-state.mjs';
const lifetimes=new WeakMap();
/** Explicit lifetime for non-React sites; presentation never grants admission. */
export function bindVisibility({state=productState,windowObject=window,documentObject=document,Observer=MutationObserver,profile='public'}={}){
 const current=lifetimes.get(state);if(current)return current;
 const root=documentObject.documentElement;
 function show(){
  const enabled=displayAllowed(state.getSnapshot());root.dataset.bookingState=enabled?'on':'off';
  documentObject.querySelectorAll('[data-booking-only]').forEach(node=>{node.hidden=!enabled;node.inert=!enabled;});
  documentObject.querySelectorAll('[data-booking-on][data-booking-off]').forEach(node=>{const text=enabled?node.dataset.bookingOn:node.dataset.bookingOff;if(node.textContent!==text)node.textContent=text;});
  windowObject.dispatchEvent(new windowObject.CustomEvent('booking:visibility',{detail:{enabled}}));
 }
 const observer=new Observer(show),unsubscribe=state.subscribe(show);
 const view=Object.freeze({enabled:()=>displayAllowed(state.getSnapshot()),refresh:state.refresh});windowObject.bookingVisibility=view;
 const stop=state.start(windowObject,documentObject,{profile});let closed=false;
 const dispose=()=>{if(closed)return;closed=true;observer.disconnect();unsubscribe();stop();lifetimes.delete(state);if(windowObject.bookingVisibility===view)delete windowObject.bookingVisibility;};
 lifetimes.set(state,dispose);show();observer.observe(root,{childList:true,subtree:true});return dispose;
}
