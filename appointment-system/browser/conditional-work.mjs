import {productState,admissionAllowed,displayAllowed,retainView} from './product-state.mjs';

/** Keep optional booking browser work unloaded and stopped while booking is OFF. */
export function startWhenBookingOn(load,{state=productState}={}){
 let revision=0,cleanup=null,active=false,closed=false;
 const permitted=()=>{const current=state.getSnapshot();return admissionAllowed(current)||(retainView(current)&&displayAllowed(current));};
 const update=()=>{
  const enabled=permitted();
  if(closed || enabled===active)return;
  active=enabled;const turn=++revision;
  if(!enabled){cleanup?.();cleanup=null;return;}
  Promise.resolve().then(load).then(start=>{
   if(!closed && turn===revision && permitted())cleanup=start();
  }).catch(()=>{
   // Durable server recovery is authoritative. A failed optional browser import
   // must not disrupt general pages or create an uncontrolled retry loop.
   if(turn===revision)active=false;
  });
 };
 const unsubscribe=state.subscribe(update);update();
 return()=>{closed=true;++revision;unsubscribe();cleanup?.();cleanup=null;};
}
