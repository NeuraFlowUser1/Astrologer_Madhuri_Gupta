// The same zero-database display controller used by the customer website.
import {productState} from './product-state.mjs';
const shell=document.querySelector('[data-booking-shell]'),absent=document.querySelector('#studio-unavailable');
function update(){
 const state=productState.getSnapshot(),enabled=state.enabled===true;
 shell.hidden=!enabled;shell.inert=!enabled;absent.hidden=enabled;
 absent.querySelector('[role="status"]').textContent=enabled?'':state.verified?'Page not found.':'This page is currently unavailable.';
 document.dispatchEvent(new CustomEvent('studio-availability',{detail:{enabled,epoch:state.activation_epoch}}));
}
window.bookingVisibility=Object.freeze({enabled:()=>productState.getSnapshot().enabled,getSnapshot:productState.getSnapshot,refresh:productState.refresh});
productState.subscribe(update);update();productState.start();
