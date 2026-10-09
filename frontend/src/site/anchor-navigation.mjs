/** One cancellable scroll operation. History remains owned by React Router. */
export function moveToTarget({target,header,focus=()=>target,top=false,smooth=false,onDone=()=>{}}){
 let frame=null,disposed=false;
 const preference=matchMedia('(prefers-reduced-motion: reduce)');
 const removals=[];
 function listen(node,event,fn,options){node.addEventListener(event,fn,options);removals.push(()=>node.removeEventListener(event,fn,options));}
 function dispose(){if(disposed)return;disposed=true;if(frame!==null)cancelAnimationFrame(frame);removals.splice(0).forEach(remove=>remove());}
 const cancel=()=>dispose();
 listen(window,'wheel',cancel,{passive:true});listen(window,'touchstart',cancel,{passive:true});listen(window,'pointerdown',cancel,{passive:true});
 listen(window,'resize',cancel);listen(window,'keydown',e=>{if(e.key==='Tab'||(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(e.key)&&!e.target.closest?.('input,textarea,select,[contenteditable]')))cancel();});
 listen(document,'visibilitychange',()=>{if(document.hidden)cancel();});listen(document,'sarsa-form-focus',cancel);listen(preference,'change',cancel);
 if(!target?.isConnected){dispose();return dispose;}
 const from=window.scrollY,barHeight=header?.getBoundingClientRect().height||0;
 const maximum=Math.max(0,document.documentElement.scrollHeight-window.innerHeight);
 const end=top?0:Math.min(maximum,Math.max(0,from+target.getBoundingClientRect().top-barHeight-(window.innerWidth<768?16:20)));
 const start=performance.now(),duration=smooth&&!preference.matches?260:0;
 function finish(){
  if(disposed)return;
  const node=focus();if(node?.isConnected)node.focus({preventScroll:true});
  dispose();onDone();
 }
 function tick(now){
  if(disposed||!target.isConnected)return dispose();
  if(header&&Math.abs(header.getBoundingClientRect().height-barHeight)>.5)return dispose();
  const progress=duration?Math.min(1,(now-start)/duration):1;
  window.scrollTo({top:from+(end-from)*(1-(1-progress)**3),behavior:'instant'});
  if(progress<1)frame=requestAnimationFrame(tick);else finish();
 }
 // Native fragment placement settles before the owned placement and focus.
 frame=requestAnimationFrame(tick);
 return dispose;
}

export function waitForTarget(id,run,{timeout=10000}={}){
 let observer,timer,frame,scroll,disposed=false,resolved=false;
 const cancel=()=>{if(disposed)return;disposed=true;observer?.disconnect();clearTimeout(timer);cancelAnimationFrame(frame);scroll?.();removals.forEach(fn=>fn());};
 const removals=[];
 const interrupt=e=>{if(e.type==='keydown'&&e.key!=='Tab'&&(!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(e.key)||e.target.closest?.('input,textarea,select,[contenteditable]')))return;if(e.type==='visibilitychange'&&!document.hidden)return;cancel();};
 for(const event of ['wheel','touchstart','pointerdown','keydown','resize']){window.addEventListener(event,interrupt,{passive:true});removals.push(()=>window.removeEventListener(event,interrupt));}
 document.addEventListener('visibilitychange',interrupt);removals.push(()=>document.removeEventListener('visibilitychange',interrupt));
 document.addEventListener('sarsa-form-focus',cancel);removals.push(()=>document.removeEventListener('sarsa-form-focus',cancel));
 const preference=matchMedia('(prefers-reduced-motion: reduce)');preference.addEventListener('change',cancel);removals.push(()=>preference.removeEventListener('change',cancel));
 function attempt(){
  const node=document.getElementById(id);if(!node||disposed||resolved)return;resolved=true;
  observer?.disconnect();clearTimeout(timer);
  // Keep cancellation live until the movement owner has installed its listeners.
  frame=requestAnimationFrame(()=>{if(disposed||!node.isConnected)return cancel();scroll=run(node);removals.splice(0).forEach(fn=>fn());});
 }
 observer=new MutationObserver(attempt);observer.observe(document.body,{childList:true,subtree:true});timer=setTimeout(cancel,timeout);attempt();return cancel;
}
