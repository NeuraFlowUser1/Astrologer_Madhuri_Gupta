/** One-shot entry timelines. No scroll-progress binding and no global selectors. */
export function mountScenes(root,definitions){
 if(!root || !definitions.length)return()=>{};
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),abort=new AbortController();
 let frame=0,hiddenAt=0,disposed=false;
 const scenes=definitions.map(d=>({...d,seen:false,active:false,start:0,progress:1}));
 const paint=(s,p)=>{
  s.progress=p;
  try{s.render(p);}catch{
   // A decorative failure must never hide the page or break navigation.
   s.active=false;s.seen=true;s.progress=1;s.element.dataset.motionFallback='true';
   for(const el of [s.element,...s.element.querySelectorAll('*')]){
    el.inert=false;
    if(el.style.opacity)el.style.opacity='1';
    if(el.style.transform)el.style.transform='none';
    if(el.style.clipPath)el.style.clipPath='none';
    if(el.style.visibility)el.style.visibility='visible';
   }
  }
  s.element.dataset.motionProgress=s.progress.toFixed(3);
 };
 const settle=s=>{s.seen=true;s.active=false;paint(s,1);};
 function tick(now){frame=0;if(disposed)return;for(const s of scenes){if(s.active){const p=Math.min(1,(now-s.start)/s.duration);paint(s,p);if(p===1)s.active=false;}}if(scenes.some(s=>s.active)&&!document.hidden)frame=requestAnimationFrame(tick);}
 function start(s){if(s.seen)return;if(reduced.matches){settle(s);return;}s.seen=true;s.active=true;s.start=performance.now();paint(s,0);if(!frame)frame=requestAnimationFrame(tick);}
 const observer=new IntersectionObserver(entries=>{for(const e of entries){const s=scenes.find(s=>s.element===e.target);if(e.isIntersecting&&e.intersectionRatio>=Math.min(.2,innerHeight/e.target.offsetHeight*.35))start(s);}},{rootMargin:'0px 0px -15% 0px',threshold:[0,.1,.2,.35]});
 for(const s of scenes){paint(s,reduced.matches?1:0);observer.observe(s.element);}
 // Essential media has a bounded wait; lower sections never wait for the hero.
 const hero=scenes[0];observer.unobserve(hero.element);
 const timer=setTimeout(()=>start(hero),1500);
 const img=hero.element.querySelector('img');
 Promise.resolve(img?.decode?.()).catch(()=>{}).then(()=>{if(!disposed){clearTimeout(timer);start(hero);}});
 root.addEventListener('focusin',e=>{const s=scenes.find(s=>s.element.contains(e.target));if(s)settle(s);},{signal:abort.signal});
 reduced.addEventListener('change',()=>{if(reduced.matches)scenes.forEach(settle);},{signal:abort.signal});
 window.addEventListener('resize',()=>scenes.forEach(s=>paint(s,s.progress)),{signal:abort.signal});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){hiddenAt=performance.now();cancelAnimationFrame(frame);frame=0;}else{const delay=performance.now()-hiddenAt;scenes.filter(s=>s.active).forEach(s=>s.start+=delay);if(scenes.some(s=>s.active))frame=requestAnimationFrame(tick);}},{signal:abort.signal});
 return()=>{disposed=true;clearTimeout(timer);cancelAnimationFrame(frame);observer.disconnect();abort.abort();scenes.forEach(settle);};
}
