import {mountScenes} from './scenes.mjs';
import {createServiceVisualMotion} from './service-visual-motion.mjs';
export function mountKundliPredictionMotion(root){
const clamp=n=>Math.max(0,Math.min(1,n)),phase=(p,a,b)=>{const q=clamp((p-a)/(b-a));return q*q*(3-2*q)};
const sections=['welcome','understand','conversation','prepare','questions','begin'].map(key=>root.querySelector('[data-kundli-scene="'+key+'"]'));
const artEnds=new Map([...root.querySelectorAll('[data-part]')].map(el=>[el,getComputedStyle(el).transform]));
function renderSection(el,p){
 const mobile=innerWidth<=650,scale=mobile?.55:1;
 if(el.id==='welcome'){
  const scene=el.querySelector('.chart-scene');
  for(const [name,x,y,r,delay] of [['back',-70,-35,-12,0],['middle',65,-20,10,.08],['front',0,55,6,.16]]){
   const part=scene.querySelector('[data-part="'+name+'"]'),q=phase(p,delay,.6+delay);
   part.style.transform=q===1?artEnds.get(part):`translate(${x*scale*(1-q)}px,${y*scale*(1-q)}px) rotate(${r*(1-q)}deg) scale(${.93+.07*q})`;
  }
  const seal=scene.querySelector('[data-part="seal"]'),q=phase(p,.48,.96);seal.style.transform=`translate(${25*(1-q)}px,${40*(1-q)}px) rotate(${60-48*q}deg) scale(${.75+.25*q})`;
  scene.querySelectorAll('.engraving path,.engraving circle').forEach(path=>{const len=path.getTotalLength();path.style.strokeDasharray=`${len} ${len}`;path.style.strokeDashoffset=len*(1-phase(p,.4,.88))});
 }else if(el.id==='conversation'){
  el.querySelector('.thread path').style.strokeDasharray='1';el.querySelector('.thread path').style.strokeDashoffset=1-phase(p,0,.8);
  el.querySelectorAll('[data-part="step"]').forEach((part,i)=>{const q=phase(p,.12+i*.12,.65+i*.12);part.style.transform=`scale(${.7+.3*q}) rotate(${-20*(1-q)}deg)`});
 }else if(el.id==='prepare'){
  el.querySelectorAll('[data-part="sheet"]').forEach((part,i)=>{const q=phase(p,i*.1,.7+i*.1);part.style.transform=q===1?artEnds.get(part):`translate(${(i-1)*45*scale*(1-q)}px,${30*scale*(1-q)}px) rotateY(${(i-1)*48*(1-q)}deg) rotate(${-9*(1-q)}deg) scale(${.88+.12*q})`});
 }else{
  el.querySelectorAll('.topic-list article,.faqs details,.closing-copy').forEach((part,i)=>{const q=phase(p,i*.09,.62+i*.09);part.style.transform=`translateY(${20*(1-q)}px)`;part.style.opacity=q});
 }
}
// Join the real marker centers at each viewport size, including the vertical phone layout.
function positionThread(){const scene=root.querySelector('.thread-scene'),svg=scene.querySelector('svg'),r=scene.getBoundingClientRect();svg.setAttribute('viewBox',`0 0 ${r.width} ${r.height}`);const points=[...scene.querySelectorAll('.step-seal')].map(el=>{const b=el.getBoundingClientRect();return {x:b.left-r.left+b.width/2,y:b.top-r.top+b.height/2}});let d=`M${points[0].x} ${points[0].y}`;for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];d+=innerWidth<=650?` C${a.x+25} ${a.y+35},${b.x-25} ${b.y-35},${b.x} ${b.y}`:` C${a.x+(b.x-a.x)*.32} ${a.y-90},${b.x-(b.x-a.x)*.32} ${b.y-90},${b.x} ${b.y}`}svg.querySelector('path').setAttribute('d',d)}positionThread();const resize=()=>positionThread();window.addEventListener('resize',resize);const visual=createServiceVisualMotion(root);const stop=mountScenes(root,[...sections.map((el,i)=>({element:el,duration:i===0?4200:2800,render:p=>{el.style.opacity=phase(p,0,.12);renderSection(el,p);}})),...visual.definitions]);return()=>{visual.dispose();stop();window.removeEventListener('resize',resize);};
}
