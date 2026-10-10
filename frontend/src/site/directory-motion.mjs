import {mountScenes} from './scenes.mjs';
const phase=(p,a,b)=>{const t=Math.max(0,Math.min(1,(p-a)/(b-a)));return t*t*(3-2*t);};
const style=(el,values)=>Object.assign(el.style,values);

/** One page owner, with independently observed cards and two visual guides. */
export function mountDirectoryMotion(root){
  const intro=root.querySelector('.service-intro');
  const definitions=[{element:intro,duration:1100,render:p=>{style(intro,{opacity:phase(p,0,.7),transform:`translateY(${12*(1-phase(p,0,1))}px)`});}}];
  for(const card of root.querySelectorAll('[data-directory-card]')){
    const photo=card.querySelector('[data-directory-part="photo"]'),motif=card.querySelector('[data-directory-part="motif"]');
    const copy=card.querySelector('[data-directory-part="copy"]'),actions=card.querySelector('[data-directory-part="actions"]');
    definitions.push({element:card,duration:2100,render:p=>{
      const a=phase(p,0,1100/2100),b=phase(p,350/2100,1450/2100),c=phase(p,600/2100,1400/2100),d=phase(p,1400/2100,1);
      style(photo,{clipPath:`inset(0 ${100*(1-a)}% 0 0 round 20px)`});
      style(motif,{opacity:b,transform:`scale(${.8+.2*b})`});
      style(copy,{opacity:c,transform:`translateY(${12*(1-c)}px)`});style(actions,{opacity:d,transform:`translateY(${8*(1-d)}px)`});
    }});
  }
  for(const guide of root.querySelectorAll('[data-directory-guide]')){
    const parts=[...guide.querySelectorAll('[data-guide-part]')],duration=guide.dataset.directoryGuide==='questions'?2400:2200;
    definitions.push({element:guide,duration,render:p=>{parts.forEach((el,i)=>{const delay=i*.07,t=phase(p,delay,Math.min(1,.62+delay));style(el,{opacity:t,transform:`translateY(${12*(1-t)}px)`});});}});
  }
  return mountScenes(root,definitions);
}
