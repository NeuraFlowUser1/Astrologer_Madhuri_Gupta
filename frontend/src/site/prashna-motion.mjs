import {mountScenes} from './scenes.mjs';
const phase=(p,a,b)=>{const t=Math.max(0,Math.min(1,(p-a)/(b-a)));return t*t*(3-2*t);};
const style=(el,values)=>Object.assign(el.style,values);

/** New page only. Entrance and ambient transforms have separate DOM owners. */
export function mountPrashnaMotion(root){
 if(!root||typeof IntersectionObserver!=='function')return()=>{};
 const hero=root.querySelector('[data-prashna-scene="hero"]'),stage=hero.querySelector('.prashna-art-stage');
 const part=name=>stage.querySelector(`[data-art-part="${name}"]`),reduced=matchMedia('(prefers-reduced-motion: reduce)'),abort=new AbortController();
 let visible=false,settled=false,examplesUsed=false;
 const ambient=()=>{stage.dataset.ambientVisible=String(visible&&settled&&!document.hidden&&!reduced.matches);};
 const definitions=[{element:hero,duration:3600,render:p=>{
  const phone=innerWidth<=650,ms=p*3600,a=phase(ms,0,700),b=phase(ms,450,1600),c=phase(ms,1100,2300),d=phase(ms,1750,2700),e=phase(ms,2300,3100);
  style(part('foundation'),{opacity:String(.25+.75*a),transform:`scale(${.96+.04*a})`,transformOrigin:'50% 50%'});
  for(const [name,sign] of [['leaf-left',-1],['leaf-right',1]])style(part(name),{transformBox:'fill-box',transformOrigin:sign<0?'100% 50%':'0% 50%',transform:`translateX(${-sign*(phone?14:24)*(1-b)}px) rotate(${sign*(phone?16:28)*(1-b)}deg) scale(${.88+.12*b})`});
  style(part('chart'),{transformBox:'fill-box',transformOrigin:'50% 50%',opacity:String(c),transform:`translateY(${(phone?18:28)*(1-c)}px) rotate(${-(phone?8:14)*(1-c)}deg)`});
  style(part('note'),{transformBox:'fill-box',transformOrigin:'50% 50%',opacity:String(d),transform:`translate(${- (phone?20:36)*(1-d)}px,${(phone?12:20)*(1-d)}px) rotate(${-(phone?5:8)*(1-d)}deg)`});
  style(part('clock'),{transformBox:'fill-box',transformOrigin:'50% 50%',opacity:String(e),transform:`translate(${(phone?22:38)*(1-e)}px,${-(phone?8:12)*(1-e)}px) rotate(${(phone?8:12)*(1-e)}deg)`});
  settled=p===1;ambient();
 }}];
 for(const section of root.querySelectorAll('[data-prashna-scene]:not([data-prashna-scene="hero"])')){
  const name=section.dataset.prashnaScene;
  const duration={difference:2800,examples:2400,preparation:2400,fee:1800,questions:600}[name];
  const render=p=>{
   if(name==='difference'){
    const image=section.querySelector('[data-prashna-part="image"]'),a=phase(p,0,900/2800);
    style(image,{opacity:String(.3+.7*a),transform:`scale(${.96+.04*a})`});
    section.querySelectorAll('[data-prashna-part="comparison"]').forEach((el,i)=>{const t=phase(p,400/2800,1500/2800);style(el,{opacity:String(t),transform:`translateX(${(i?28:-28)*(1-t)}px) rotate(${(i?3:-3)*(1-t)}deg)`});const label=el.querySelector('h3'),l=phase(p,1200/2800,2200/2800);style(label,{opacity:String(l),transform:`translateY(${8*(1-l)}px)`});});
   }else if(name==='examples'){
    if(examplesUsed)p=1;
    section.querySelectorAll('[role="tab"]').forEach((el,i)=>{const t=phase(p,i*70/2400,(700+i*70)/2400);style(el,{opacity:String(t),transform:`translateY(${10*(1-t)}px)`});});
    section.querySelectorAll('.example-sheet').forEach((el,i)=>{const t=phase(p,500/2400,1500/2400),copy=phase(p,1000/2400,2000/2400);style(el,{opacity:String(t),transform:`translateX(${(i?20:-20)*(1-t)}px) rotate(${(i?2:-2)*(1-t)}deg)`});style(el.firstElementChild,{opacity:String(copy)});});
   }else if(name==='preparation'){
    section.querySelectorAll('.prep-step').forEach((el,i)=>{const a=phase(p,i*70/2400,(850+i*70)/2400),b=phase(p,400/2400,1500/2400);style(el.querySelector('.prep-number'),{opacity:String(a),transform:`translateY(${12*(1-a)}px)`});style(el.querySelector('.prep-copy'),{opacity:String(b),transformOrigin:'50% 0%',transform:`translateY(${14*(1-b)}px) scaleY(${.96+.04*b})`});});
   }else if(name==='fee'){
    const a=phase(p,0,650/1800);style(section.querySelector('.chapter-intro'),{opacity:String(a),transform:`translateY(${10*(1-a)}px)`});
    section.querySelectorAll('.amount-example').forEach((el,i)=>{const t=phase(p,(350+i*70)/1800,(1150+i*70)/1800);style(el,{opacity:String(t),transform:`translateY(${12*(1-t)}px)`});});
    const fact=section.querySelector('[data-prashna-part="appointment"]'),t=phase(p,900/1800,1450/1800);if(fact)style(fact,{opacity:String(t)});
   }else{const t=phase(p,0,1);style(section.querySelector('.prashna-wrap'),{opacity:String(t),transform:`translateY(${12*(1-t)}px)`});}
  };
  definitions.push({element:section,duration,render});
  if(name==='examples')root.addEventListener('prashna:topic',()=>{examplesUsed=true;render(1);},{signal:abort.signal});
 }
 let observer;
 try{observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;ambient();},{threshold:.15});observer.observe(stage);}catch{observer?.disconnect();abort.abort();stage.dataset.ambientVisible='false';return()=>{};}
 document.addEventListener('visibilitychange',ambient,{signal:abort.signal});reduced.addEventListener('change',ambient,{signal:abort.signal});
 let stop;
 try{stop=mountScenes(root,definitions);}catch{observer.disconnect();abort.abort();definitions.forEach(scene=>scene.render(1));stage.dataset.ambientVisible='false';return()=>{};}
 return()=>{stop();observer.disconnect();abort.abort();stage.dataset.ambientVisible='false';};
}
