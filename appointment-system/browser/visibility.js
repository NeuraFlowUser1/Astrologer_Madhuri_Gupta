/* Optional non-React binding. Load as a module; both bindings use one store. */
import {productState} from './product-state.mjs';
const root=document.documentElement;
function show(){
 const {enabled}=productState.getSnapshot();root.dataset.bookingState=enabled?'on':'off';
 document.querySelectorAll('[data-booking-only]').forEach(node=>{
  node.hidden=!enabled;node.inert=!enabled;
 });
 document.querySelectorAll('[data-booking-on][data-booking-off]').forEach(node=>{
  const text=enabled?node.dataset.bookingOn:node.dataset.bookingOff;
  if(node.textContent!==text)node.textContent=text;
 });
 dispatchEvent(new CustomEvent('booking:visibility',{detail:{enabled}}));
}
productState.subscribe(show);
window.bookingVisibility=Object.freeze({enabled:()=>productState.getSnapshot().enabled,refresh:productState.refresh});
show();productState.start();
new MutationObserver(show).observe(root,{childList:true,subtree:true});
