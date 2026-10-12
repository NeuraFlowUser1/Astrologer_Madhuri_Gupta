/** Optional paper assembly. Visible static content is always the baseline. */
export function mountCertificationsMotion(root){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),animations=new Set();
  let observer,seen=false,disposed=false;
  const settle=()=>{for(const animation of animations)animation.cancel();animations.clear();};
  function animate(element,frames,options){
    if(!element||typeof element.animate!=='function')return;
    const animation=element.animate(frames,{easing:'cubic-bezier(.2,.7,.2,1)',...options});
    animations.add(animation);
    if(document.hidden)animation.pause();
    animation.finished.then(()=>animations.delete(animation),()=>animations.delete(animation));
  }
  function enter(){
    if(disposed||seen)return;
    seen=true;
    if(reduced.matches)return;
    animate(root.querySelector('.certifications-rule'),[{scale:'0 1'},{scale:'1 1'}],{duration:450});
    root.querySelectorAll('.certificate-item').forEach((item,index)=>{
      animate(item.querySelector('.certificate-preview'),[{opacity:.45,transform:`translateY(22px) rotate(${index%2?1.5:-1.5}deg)`},{opacity:1,transform:'translateY(0) rotate(0)'}],{duration:650,delay:110*index});
      animate(item.querySelector('.certificate-caption'),[{opacity:.5,translate:'0 12px'},{opacity:1,translate:'0 0'}],{duration:400,delay:260+110*index});
    });
  }
  const focus=()=>{seen=true;settle();};
  const motionChange=()=>{if(reduced.matches)focus();};
  const visibility=()=>{for(const animation of animations){if(document.hidden)animation.pause();else animation.play();}};
  try{if(typeof IntersectionObserver==='function'){
    observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))enter();},{threshold:.12});
    observer.observe(root);
  }}catch{observer?.disconnect();observer=null;}
  root.addEventListener('focusin',focus);
  reduced.addEventListener('change',motionChange);
  document.addEventListener('visibilitychange',visibility);
  return()=>{disposed=true;observer?.disconnect();root.removeEventListener('focusin',focus);reduced.removeEventListener('change',motionChange);document.removeEventListener('visibilitychange',visibility);settle();};
}
