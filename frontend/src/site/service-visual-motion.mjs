const clamp=n=>Math.max(0,Math.min(1,n));
const phase=(p,a,b)=>{const t=clamp((p-a)/(b-a));return t*t*(3-2*t);};
const style=(el,values)=>Object.assign(el.style,values);

/** New story definitions join the existing page owner; original heroes stay first. */
export function createServiceVisualMotion(root){
  const story=root.querySelector('[data-visual-stage]');
  if(!story)return{definitions:[],dispose(){}};
  const photo=story.querySelector('[data-visual-part="photo"]'),markers=story.querySelector('[data-visual-part="markers"]');
  const copy=story.querySelector('[data-visual-part="copy"]'),controls=story.querySelector('[data-visual-part="controls"]');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),lights=[...story.querySelectorAll('[data-visual-ambient]')];
  const animations=[];let disposed=false,settled=false,visible=false,focused=false,interacting=false,observer;
  function sync(){
    if(disposed)return;
    const running=settled&&visible&&!document.hidden&&!reduced.matches&&!focused&&!interacting;
    story.dataset.ambientRunning=String(running&&animations.length>0);
    animations.forEach(a=>{try{if(running)a.play();else a.pause();}catch{/* Optional light leaves the illustration readable. */}});
  }
  try{
    const id=story.dataset.serviceId;
    for(const [i,light] of lights.entries()){
      let duration,frames;
      if(id==='numerology'){
        duration=18000;
        frames=Array.from({length:181},(_,k)=>{const local=(k/180*duration-i*6000)/6000;return{offset:k/180,opacity:local<0||local>1?0:.24*phase(local,0,.12)*(1-phase(local,.85,1))};});
      }else{
        const settings=id==='kundli-matching'?[14000,.12,.34]:id==='kundli-prediction'?[12000,.08,.30]:[16000,.06,.22];
        duration=settings[0];frames=[{opacity:settings[1]},{opacity:settings[2]},{opacity:settings[1]}];
      }
      const animation=light.animate(frames,{duration,iterations:Infinity,easing:id==='numerology'?'linear':'ease-in-out'});animation.pause();animations.push(animation);
    }
    observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();},{threshold:0});observer.observe(photo);
  }catch{observer?.disconnect();animations.forEach(a=>a.cancel());animations.length=0;}
  const focusIn=()=>{focused=true;sync();};
  const focusOut=e=>{focused=story.contains(e.relatedTarget);sync();};
  const pointerDown=()=>{interacting=true;sync();};
  const pointerUp=()=>{interacting=false;sync();};
  story.addEventListener('focusin',focusIn);story.addEventListener('focusout',focusOut);story.addEventListener('pointerdown',pointerDown);
  window.addEventListener('pointerup',pointerUp);window.addEventListener('pointercancel',pointerUp);
  document.addEventListener('visibilitychange',sync);reduced.addEventListener('change',sync);
  return{
    definitions:[{element:story,duration:2600,render:p=>{
      const a=phase(p,0,1200/2600),b=phase(p,600/2600,1800/2600),c=phase(p,1200/2600,1);
      style(photo,{clipPath:`inset(0 ${100*(1-a)}% 0 0 round 24px)`});
      style(markers,{opacity:b,transform:`translateY(${12*(1-b)}px)`});
      for(const el of [copy,controls])style(el,{opacity:c,transform:`translateY(${16*(1-c)}px)`});
      const now=p===1;if(now!==settled){settled=now;sync();}
    }}],
    // Dispose before mountScenes' final paint can settle a never-seen story.
    dispose(){disposed=true;observer?.disconnect();animations.forEach(a=>a.cancel());story.dataset.ambientRunning='false';story.removeEventListener('focusin',focusIn);story.removeEventListener('focusout',focusOut);story.removeEventListener('pointerdown',pointerDown);window.removeEventListener('pointerup',pointerUp);window.removeEventListener('pointercancel',pointerUp);document.removeEventListener('visibilitychange',sync);reduced.removeEventListener('change',sync);}
  };
}
