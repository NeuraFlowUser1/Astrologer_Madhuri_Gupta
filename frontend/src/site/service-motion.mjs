import {mountScenes} from './scenes.mjs';
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
  // A wall rises, the floor unfolds, then the small house finds its place.
  const wall=phase(p,0,.5),floor=phase(p,.27,.76),house=phase(p,.64,1);
  style(parts[0],{opacity:wall,transformOrigin:'bottom',transform:`perspective(650px) rotateX(${55*(1-wall)}deg) translateY(${35*(1-wall)}px)`});
  style(parts[1],{opacity:floor,transformOrigin:'top left',transform:`perspective(650px) rotateX(${-70*(1-floor)}deg) scaleY(${.2+.8*floor})`});
  style(parts[2],{opacity:house,transform:`translateY(${45*(1-house)}px) scale(${.8+.2*house})`});
 }else{
  // Number slips settle one by one, then separate gently into a readable rhythm.
  parts.forEach((el,i)=>{const arrival=phase(p,i*.13,.5+i*.13),fan=phase(p,.65,1);style(el,{opacity:arrival,transform:`translate(${(i-1)*12*fan}px,${65*(1-arrival)}px) rotate(${(i-1)*5*fan}deg)`});});
 }
}
export function mountServiceMotion(root,art){
 const sections=[...root.querySelectorAll('section')];
 return mountScenes(root,sections.map((element,index)=>({element,duration:index===0?3000:2200,render:p=>{
  if(index===0){hero(element,p,art);return;}
  const layers=[...element.querySelectorAll('[data-layer]')];
  layers.forEach((el,i)=>{
   const t=phase(p,i*.14,.65+i*.14);
   if(index===1)style(el,{opacity:t,transform:`translateY(${26*(1-t)}px)`,borderTopColor:`rgba(140,157,126,${t})`});
   else style(el,{opacity:t,transformOrigin:'left center',transform:`perspective(750px) rotateY(${-24*(1-t)}deg) translateX(${-20*(1-t)}px)`});
  });
  element.querySelectorAll('[data-copy]').forEach(el=>{const t=phase(p,index===3?0:.45,1);style(el,{opacity:t,transform:`translateY(${18*(1-t)}px)`});});
 }})));
}
