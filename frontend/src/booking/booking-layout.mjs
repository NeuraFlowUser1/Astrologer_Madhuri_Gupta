/** Booking-owned geometry uses the connected public bar, never a guessed height. */
export function mountBookingLayout(root,onStep,{headerBar}={}){
 const strip=root?.querySelector('.journey-nav');
 const sections=['service','appointment','details','review'].map(id=>root?.querySelector('#'+id));
 if(!root?.isConnected||!headerBar?.isConnected||!strip||sections.some(section=>!section)){
  console.error('Sarsa booking layout: connected public bar and four sections are required.');
  return {go(){},dispose(){}};
 }
 let observer,frame=null,headerHeight=-1,stripHeight=-1,disposed=false;
 const preference=matchMedia('(prefers-reduced-motion: reduce)');
 const cancel=()=>{if(frame!==null)cancelAnimationFrame(frame);frame=null;};
 function measure(){
  if(disposed)return;const nextHeader=headerBar.getBoundingClientRect().height,nextStrip=strip.getBoundingClientRect().height;
  if(nextHeader===headerHeight&&nextStrip===stripHeight)return;
  cancel();headerHeight=nextHeader;stripHeight=nextStrip;
  root.style.setProperty('--booking-header-height',headerHeight+'px');root.style.setProperty('--booking-strip-height',stripHeight+'px');
  observer?.disconnect();const visible=new Map();
  observer=new IntersectionObserver(entries=>{
   for(const entry of entries)visible.set(entry.target,entry.isIntersecting);
   const current=sections.filter(section=>visible.get(section)).at(-1);if(current)onStep(current.id);
  },{rootMargin:`-${Math.ceil(headerHeight+stripHeight)}px 0px -45% 0px`,threshold:[0,.1]});
  sections.forEach(section=>observer.observe(section));
 }
 const resize=new ResizeObserver(measure);resize.observe(headerBar);resize.observe(strip);measure();
 const removals=[];
 function listen(node,event,fn,options){node.addEventListener(event,fn,options);removals.push(()=>node.removeEventListener(event,fn,options));}
 listen(window,'wheel',cancel,{passive:true});listen(window,'touchstart',cancel,{passive:true});listen(window,'pointerdown',cancel,{passive:true});listen(window,'resize',cancel);
 listen(window,'keydown',event=>{if(event.key==='Tab'||(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key)&&!event.target.closest?.('input,textarea,select,[contenteditable]')))cancel();});
 listen(document,'visibilitychange',()=>{if(document.hidden)cancel();});listen(preference,'change',cancel);
 return {go(id){
  if(disposed)return;const section=sections.find(value=>value.id===id);if(!section)return;cancel();
  const gap=window.innerWidth<768?16:20,maximum=Math.max(0,document.documentElement.scrollHeight-window.innerHeight);
  const target=Math.min(maximum,Math.max(0,window.scrollY+section.getBoundingClientRect().top-headerHeight-stripHeight-gap));
  const from=window.scrollY,start=performance.now(),duration=preference.matches?0:220;onStep(id);
  const finish=()=>{if(section.isConnected)section.querySelector('h2')?.focus({preventScroll:true});};
  if(!duration){window.scrollTo({top:target,behavior:'instant'});finish();return;}
  function tick(now){if(disposed||!section.isConnected)return cancel();const progress=Math.min(1,(now-start)/duration);window.scrollTo({top:from+(target-from)*(1-(1-progress)**3),behavior:'instant'});
   frame=progress<1?requestAnimationFrame(tick):null;if(progress===1)finish();}
  frame=requestAnimationFrame(tick);
 },dispose(){disposed=true;cancel();resize.disconnect();observer?.disconnect();removals.forEach(remove=>remove());}};
}
