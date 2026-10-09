/** Booking-owned geometry uses the connected public bar, never a guessed height. */
export function mountBookingLayout(root,onStep,{headerBar}={}){
 const strip=root?.querySelector('.journey-nav');
 const sections=['service','appointment','details','review'].map(id=>root?.querySelector('#'+id));
 if(!root?.isConnected||!headerBar?.isConnected||!strip||sections.some(section=>!section)){
  console.error('Sarsa booking layout: connected public bar and four sections are required.');
  return {go(){},dispose(){}};
 }
 let observer,resize,frame=null,headerHeight=-1,stripHeight=-1,disposed=false,observationEpoch=0,scrollEpoch=0;
 let preference;try{const media=typeof matchMedia==='function'?matchMedia('(prefers-reduced-motion: reduce)'):null;preference=typeof media?.matches==='boolean'&&typeof media.addEventListener==='function'&&typeof media.removeEventListener==='function'?media:null;}catch{preference=null;}
 const cancel=()=>{const pending=frame;frame=null;scrollEpoch++;if(pending!==null)try{cancelAnimationFrame(pending);}catch{/* A queued callback also checks its epoch. */}};
 function releaseIntersection(){const previous=observer;observer=null;observationEpoch++;try{previous?.disconnect();}catch{/* Released callbacks are inert even when native cleanup fails. */}}
 function releaseResize(){const previous=resize;resize=null;try{previous?.disconnect();}catch{/* Released callbacks are inert even when native cleanup fails. */}}
 function readStep(){
  if(disposed)return;
  const top=headerHeight+stripHeight,bottom=top+(window.innerHeight-top)*.55;
  const current=sections.filter(section=>{const r=section.getBoundingClientRect();return r.top<bottom&&r.bottom>top;}).at(-1);if(current)onStep(current.id);
 }
 function measure(){
  if(disposed)return;const nextHeader=headerBar.getBoundingClientRect().height,nextStrip=strip.getBoundingClientRect().height;
  if(nextHeader===headerHeight&&nextStrip===stripHeight)return;
  cancel();headerHeight=nextHeader;stripHeight=nextStrip;
  root.style.setProperty('--booking-header-height',headerHeight+'px');root.style.setProperty('--booking-strip-height',stripHeight+'px');
  releaseIntersection();const currentEpoch=observationEpoch,visible=new Map();
  try{if(typeof IntersectionObserver!=='function')throw Error('no_intersection_observer');observer=new IntersectionObserver(entries=>{
   if(disposed||currentEpoch!==observationEpoch)return;
   for(const entry of entries)visible.set(entry.target,entry.isIntersecting);
   const current=sections.filter(section=>visible.get(section)).at(-1);if(current)onStep(current.id);
  },{rootMargin:`-${Math.ceil(headerHeight+stripHeight)}px 0px -45% 0px`,threshold:[0,.1]});
  sections.forEach(section=>observer.observe(section));}catch{releaseIntersection();readStep();}
 }
 try{if(typeof ResizeObserver==='function'){let candidate;candidate=new ResizeObserver(()=>{if(candidate&&resize===candidate)measure();});resize=candidate;resize.observe(headerBar);resize.observe(strip);}}catch{releaseResize();}measure();
 const removals=[];
 function listen(node,event,fn,options){
  let active=true;const listener=(...args)=>{if(active&&!disposed)fn(...args);};
  const remove=()=>{active=false;try{node.removeEventListener(event,listener,options);}catch{/* The local guard deactivates a retained native listener. */}};
  try{node.addEventListener(event,listener,options);removals.push(remove);}catch{preference=null;remove();}
 }
 listen(window,'wheel',cancel,{passive:true});listen(window,'touchstart',cancel,{passive:true});listen(window,'pointerdown',cancel,{passive:true});listen(window,'resize',()=>{cancel();measure();if(!observer)readStep();});listen(window,'scroll',()=>{if(!observer)readStep();},{passive:true});
 if(typeof document.fonts?.addEventListener==='function')listen(document.fonts,'loadingdone',measure);
 listen(window,'keydown',event=>{if(event.key==='Tab'||(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key)&&!event.target.closest?.('input,textarea,select,[contenteditable]')))cancel();});
 listen(document,'visibilitychange',()=>{if(document.hidden)cancel();});if(preference)listen(preference,'change',cancel);
 return {go(id){
  if(disposed)return;const section=sections.find(value=>value.id===id);if(!section)return;cancel();
  const gap=window.innerWidth<768?16:20,maximum=Math.max(0,document.documentElement.scrollHeight-window.innerHeight);
  const target=Math.min(maximum,Math.max(0,window.scrollY+section.getBoundingClientRect().top-headerHeight-stripHeight-gap));
  const from=window.scrollY,start=performance.now(),duration=!preference||preference.matches||typeof requestAnimationFrame!=='function'||typeof cancelAnimationFrame!=='function'?0:220,currentEpoch=scrollEpoch;onStep(id);
  const finish=()=>{if(section.isConnected)section.querySelector('h2')?.focus({preventScroll:true});};
  if(!duration){window.scrollTo({top:target,behavior:'instant'});finish();return;}
  function tick(now){if(disposed||currentEpoch!==scrollEpoch)return;if(!section.isConnected)return cancel();const progress=Math.min(1,(now-start)/duration);window.scrollTo({top:from+(target-from)*(1-(1-progress)**3),behavior:'instant'});
   frame=progress<1?requestAnimationFrame(tick):null;if(progress===1)finish();}
  frame=requestAnimationFrame(tick);
 },dispose(){if(disposed)return;disposed=true;cancel();releaseResize();releaseIntersection();removals.splice(0).forEach(remove=>remove());}};
}
