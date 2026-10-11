/** One decorative owner; no booking state, scene replay or global ticker. */
export function mountBookingOrnament(root){
 if(!root)return()=>{};
 const scope=root.closest('main')||root.parentElement,reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let visible=false,assembled=false,disposed=false;const animations=[];
 const focused=()=>scope?.contains(document.activeElement)&&!!document.activeElement?.closest('form');
 function update(){
  if(disposed)return;
  const running=visible&&document.visibilityState!=='hidden'&&!focused()&&!reduced.matches;
  root.dataset.motion=running?'running':'paused';
  if(running&&!assembled){
   assembled=true;
   if(typeof root.animate==='function'){
    for(const line of root.querySelectorAll('[data-art="orbit"] circle'))animations.push(line.animate(
     [{strokeDasharray:'1',strokeDashoffset:'1'},{strokeDasharray:'1',strokeDashoffset:'0'}],{duration:400,easing:'cubic-bezier(.2,.7,.2,1)'}));
    for(const line of root.querySelectorAll('[data-art="kundli"] path'))animations.push(line.animate(
     [{strokeDasharray:'1',strokeDashoffset:'1'},{strokeDasharray:'1',strokeDashoffset:'0'}],{duration:360,delay:400,fill:'backwards',easing:'cubic-bezier(.2,.7,.2,1)'}));
    const points=root.querySelector('[data-art="points"]');
    animations.push(points.animate([{opacity:0,transform:'scale(.6)'},{opacity:1,transform:'scale(1)'}],
     {duration:240,delay:760,fill:'backwards',easing:'cubic-bezier(.2,.7,.2,1)'}));
   }
  }
  for(const animation of animations){if(reduced.matches)animation.cancel();else if(animation.playState!=='finished')running?animation.play():animation.pause();}
 }
 const observer=typeof IntersectionObserver==='function'?new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;update();},{threshold:.05}):null;
 if(observer)observer.observe(root);else visible=true;
 const focusChange=()=>queueMicrotask(update);
 document.addEventListener('visibilitychange',update);scope?.addEventListener('focusin',focusChange);scope?.addEventListener('focusout',focusChange);
 reduced.addEventListener('change',update);update();
 return()=>{disposed=true;observer?.disconnect();animations.forEach(animation=>animation.cancel());delete root.dataset.motion;
  document.removeEventListener('visibilitychange',update);scope?.removeEventListener('focusin',focusChange);scope?.removeEventListener('focusout',focusChange);reduced.removeEventListener('change',update);};
}
