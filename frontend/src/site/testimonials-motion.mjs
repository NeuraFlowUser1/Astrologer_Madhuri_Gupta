/** Page-local motion. React owns content; the shared public scroller owns navigation. */
export function mountTestimonialsMotion(root){
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  const ambient=root.querySelector('[data-ambient]'),opening=root.querySelector('[data-scene=opening]');
  const animations=new Set(),channels=new Map(),seen=new WeakSet();
  let disposed=false,observer,ambientVisible=false,openingSettled=false,readerOpen=false;
  const syncAmbient=()=>{
    if(disposed)return;
    ambient?.classList.toggle('is-running',openingSettled&&ambientVisible&&!document.hidden&&!reduced.matches&&!readerOpen&&!opening.contains(document.activeElement));
  };
  function animate(element,frames,options){
    if(disposed||!element||reduced.matches||typeof element.animate!=='function')return null;
    const animation=element.animate(frames,{easing:'cubic-bezier(.2,.7,.2,1)',...options});
    animations.add(animation);
    if(document.hidden)animation.pause();
    animation.finished.then(()=>animations.delete(animation),()=>animations.delete(animation));
    return animation;
  }
  function settleWithin(element){
    for(const animation of animations)if(element.contains(animation.effect?.target))animation.cancel();
  }
  function change(channel,selector,duration,offset){
    channels.get(channel)?.cancel();
    channels.set(channel,animate(root.querySelector(selector),[{opacity:.4,translate:`0 ${offset}px`},{opacity:1,translate:'0 0'}],{duration}));
  }
  function grid(duration,stagger,cap,offset){
    const container=root.querySelector('#story-grid');
    settleWithin(container);
    container.querySelectorAll('.story-card').forEach((card,index)=>animate(card,[{opacity:.35,translate:`0 ${offset}px`},{opacity:1,translate:'0 0'}],{duration,delay:Math.min(index*stagger,cap)}));
  }
  function enter(scene){
    const name=scene.dataset.scene;
    if(scene.contains(document.activeElement)){
      if(name==='opening'){openingSettled=true;syncAmbient();}
      return;
    }
    if(name==='opening'){
      animate(scene.querySelector('.thread-draw'),[{strokeDasharray:'1000',strokeDashoffset:1000},{strokeDasharray:'1000',strokeDashoffset:0}],{duration:700});
      scene.querySelectorAll('[data-paper]').forEach((paper,index)=>animate(paper,[{opacity:.3,translate:`0 ${25-index*4}px`},{opacity:1,translate:'0 0'}],{duration:750,delay:150+index*120}));
      const last=animate(scene.querySelector('.opening-star'),[{opacity:0,scale:'.3'},{opacity:1,scale:'1'}],{duration:500,delay:900});
      const settled=()=>{if(!disposed){openingSettled=true;syncAmbient();}};
      if(last)last.finished.then(settled,settled);else settled();
    }else if(name==='featured'){
      animate(scene.querySelector('[data-enter=photo]'),[{clipPath:'inset(0 100% 0 0 round 24px)'},{clipPath:'inset(0 0 0 0 round 24px)'}],{duration:650});
      animate(scene.querySelector('[data-enter=quote]'),[{opacity:.3,translate:'0 16px'},{opacity:1,translate:'0 0'}],{duration:700,delay:350});
    }else if(name==='collection')grid(450,70,280,15);
    else if(name==='echoes'){
      animate(scene.querySelector('.echo-line path'),[{strokeDasharray:'600',strokeDashoffset:600},{strokeDasharray:'600',strokeDashoffset:0}],{duration:800});
      animate(scene.querySelector('[data-enter=echo]'),[{opacity:.3,translate:'0 12px'},{opacity:1,translate:'0 0'}],{duration:650,delay:300});
    }else if(name==='invitation'){
      animate(scene.querySelector('.invitation-path'),[{strokeDasharray:'500',strokeDashoffset:500},{strokeDasharray:'500',strokeDashoffset:0}],{duration:950});
      animate(scene.querySelector('.sun-lines'),[{opacity:.3,scale:'.9'},{opacity:1,scale:'1'}],{duration:750});
    }
  }
  try{
    if(typeof IntersectionObserver==='function'){
      observer=new IntersectionObserver(entries=>{
        if(disposed)return;
        for(const entry of entries){
          if(entry.target===ambient){ambientVisible=entry.isIntersecting;syncAmbient();}
          else if(entry.isIntersecting&&!seen.has(entry.target)){seen.add(entry.target);enter(entry.target);}
        }
      },{threshold:.08});
      if(ambient)observer.observe(ambient);
      root.querySelectorAll('[data-scene]').forEach(scene=>observer.observe(scene));
    }
  }catch{observer?.disconnect();observer=null;}
  const focusIn=event=>{const scene=event.target.closest('[data-scene]');if(scene&&root.contains(scene))settleWithin(scene);syncAmbient();};
  const focusOut=()=>queueMicrotask(syncAmbient);
  const visibility=()=>{
    for(const animation of animations){if(document.hidden)animation.pause();else if(animation.playState==='paused')animation.play();}
    syncAmbient();
  };
  const preference=()=>{if(reduced.matches)for(const animation of animations)animation.cancel();syncAmbient();};
  root.addEventListener('focusin',focusIn);root.addEventListener('focusout',focusOut);
  document.addEventListener('visibilitychange',visibility);reduced.addEventListener('change',preference);
  return {
    updateGrid:()=>grid(260,35,140,10),
    updateFeature:()=>change('feature','#featured-story',200,8),
    updateTheme:()=>change('theme','.echo-content',180,6),
    setReaderOpen:open=>{readerOpen=open;syncAmbient();},
    dispose(){
      disposed=true;observer?.disconnect();
      for(const animation of animations)animation.cancel();
      animations.clear();channels.clear();ambient?.classList.remove('is-running');
      root.removeEventListener('focusin',focusIn);root.removeEventListener('focusout',focusOut);
      document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',preference);
    },
  };
}
