import {mountScenes} from './scenes.mjs';
import {createServiceVisualMotion} from './service-visual-motion.mjs';
import {createVastuPrinciplesScene} from './vastu-motion.mjs';
const phase=(p,a,b)=>{const t=Math.max(0,Math.min(1,(p-a)/(b-a)));return t*t*(3-2*t);};
const style=(el,values)=>Object.assign(el.style,values);

function hero(element,p,art){
 const parts=[...element.querySelectorAll('[data-layer]')];
 const distance=innerWidth<650?45:75;
 if(art==='matching'){
  // Two separate charts arrive, overlap, then the shared seal completes the pair.
  parts.slice(0,2).forEach((el,i)=>{const t=phase(p,i*.18,.6+i*.18);style(el,{opacity:t,transform:`translateX(${(i?1:-1)*distance*(1-t)}px) rotate(${(i?1:-1)*35*(1-t)}deg)`});});
  const seal=phase(p,.68,1);style(parts[2],{opacity:seal,transform:`scale(${.4+.6*seal}) rotate(${-55*(1-seal)}deg)`});
 }else if(art==='vastu'){
  // The material surface, home illustration and finishing caption arrive in order.
  const surface=phase(p,0,.4),home=phase(p,.2,.8),detail=phase(p,1900/3000,1);
  style(parts[0],{opacity:surface});
  style(parts[1],{opacity:home,transform:`translateY(${24*(1-home)}px) scale(${.98+.02*home})`});
  style(parts[2],{opacity:detail,transform:`translateY(${8*(1-detail)}px)`});
 }else{
  // Number slips settle one by one, then separate gently into a readable rhythm.
  parts.forEach((el,i)=>{const arrival=phase(p,i*.13,.5+i*.13),fan=phase(p,.65,1);style(el,{opacity:arrival,transform:`translate(${(i-1)*12*fan}px,${65*(1-arrival)}px) rotate(${(i-1)*5*fan}deg)`});});
 }
}
export function mountServiceMotion(root,art){
 const sections=['hero','topics','prepare','book'].map(key=>root.querySelector('[data-service-scene="'+key+'"]'));
 const visual=createServiceVisualMotion(root);
 const principles=createVastuPrinciplesScene(root);
 const stop=mountScenes(root,[...sections.map((element,index)=>({element,duration:index===0?3000:2200,render:p=>{
  if(index===0){hero(element,p,art);return;}
  const layers=[...element.querySelectorAll('[data-layer]')];
  layers.forEach((el,i)=>{
   const t=phase(p,i*.14,.65+i*.14);
   if(index===1)style(el,{opacity:t,transform:`translateY(${26*(1-t)}px)`,borderTopColor:`rgba(140,157,126,${t})`});
   else style(el,{opacity:t,transformOrigin:'left center',transform:`perspective(750px) rotateY(${-24*(1-t)}deg) translateX(${-20*(1-t)}px)`});
  });
  element.querySelectorAll('[data-copy]').forEach(el=>{const t=phase(p,index===3?0:.45,1);style(el,{opacity:t,transform:`translateY(${18*(1-t)}px)`});});
 }})),...visual.definitions,...principles]);
 return()=>{visual.dispose();stop();};
}
