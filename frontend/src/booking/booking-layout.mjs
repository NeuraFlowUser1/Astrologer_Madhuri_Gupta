/** Booking-owned measurements and one cancellable navigation animation. */
export function mountBookingLayout(root,onStep){
 const header=root.querySelector('.site-header'),strip=root.querySelector('.journey-nav');
 const sections=['service','appointment','details','review'].map(id=>root.querySelector('#'+id));
 let observer,frame=null,headerHeight=0,stripHeight=0,disposed=false;
 const cancel=()=>{if(frame!==null)cancelAnimationFrame(frame);frame=null;};
 function measure(){
  headerHeight=header.getBoundingClientRect().height;stripHeight=strip.getBoundingClientRect().height;
  root.style.setProperty('--booking-header-height',headerHeight+'px');root.style.setProperty('--booking-strip-height',stripHeight+'px');
  observer?.disconnect();const visible=new Map();
  observer=new IntersectionObserver(entries=>{
   for(const entry of entries)visible.set(entry.target,entry.isIntersecting);
   const current=sections.filter(section=>visible.get(section)).at(-1);if(current)onStep(current.id);
  },{rootMargin:`-${Math.ceil(headerHeight+stripHeight)}px 0px -45% 0px`,threshold:[0,.1]});
  for(const section of sections)observer.observe(section);
 }
 const resize=new ResizeObserver(measure);resize.observe(header);resize.observe(strip);measure();
 window.addEventListener('wheel',cancel,{passive:true});window.addEventListener('touchstart',cancel,{passive:true});
 return {go(id){
  if(disposed)return;const section=sections.find(value=>value.id===id);if(!section)return;cancel();
  const gap=window.innerWidth<768?16:20,target=Math.max(0,window.scrollY+section.getBoundingClientRect().top-headerHeight-stripHeight-gap);
  const from=window.scrollY,start=performance.now(),duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:220;
  section.querySelector('h2')?.focus({preventScroll:true});onStep(id);
  if(!duration){window.scrollTo({top:target,behavior:'instant'});return;}
  function tick(now){const progress=Math.min(1,(now-start)/duration);window.scrollTo({top:from+(target-from)*(1-(1-progress)**3),behavior:'instant'});
   frame=progress<1?requestAnimationFrame(tick):null;}
  frame=requestAnimationFrame(tick);
 },dispose(){disposed=true;cancel();resize.disconnect();observer?.disconnect();window.removeEventListener('wheel',cancel);window.removeEventListener('touchstart',cancel);}};
}
