import {mountScenes} from './scenes.mjs';
export function mountHomeMotion(root){
const clamp=n=>Math.max(0,Math.min(1,n));const ease=n=>{const t=clamp(n);return t*t*(3-2*t)};const phase=(p,a,b)=>ease((p-a)/(b-a));
const sections=[...root.querySelectorAll('[data-chapter]')];
const by=id=>root.querySelector('#'+id);const qs=s=>root.querySelector(s);
const set=(selector,values)=>Object.assign(qs(selector).style,values);
const sceneProgress=new Map();
function progress(section){return sceneProgress.get(section)??0}
function update(){const m=innerWidth<=700,g=progress(by('welcome')),e=progress(by('madhuri')),h=progress(by('conversation')),i=progress(by('process')),b=progress(by('questions'));const G=ease(g);
 set('.hero-foreground.left',{transform:`translateX(${-110*G}%) rotate(${-5*G}deg)`});set('.hero-foreground.right',{transform:`translateX(${110*G}%) rotate(${5*G}deg)`});set('.hero-photo',{transform:`scale(${1.035-.035*G})`});
 set('.about-image',{clipPath:`circle(${9+ease(e)*80}% at 50% 50%)`,transform:`translateY(${20*(1-ease(e))}px)`});
 const a=phase(h,0,.48),z=phase(h,.5,1),c=phase(h,.22,.75);set('.forest-reveal',{clipPath:`circle(${c*110}% at 60% 50%)`});
 set('.shared-disc',{left:(m?70-28*a-27*z:72-27*a-27*z)+'%',top:(m?35-8*a-13*z:24+6*z)+'%',transform:`scale(${1+.13*Math.sin(Math.PI*ease(h))}) rotate(${-25*ease(h)}deg)`});
 set('.connection-start',{opacity:1-phase(h,.13,.47),transform:`translateY(${-20*a}px)`});set('.connection-end',{opacity:phase(h,.55,.95),transform:`translateY(${26*(1-z)}px)`});set('.disc-orbit',{opacity:z});
 const I=ease(i);root.querySelectorAll('.steps article').forEach((card,k)=>card.style.transform=m?`translateX(${(k%2?1:-1)*18*(1-I)}px)`:`translateX(${(1-k)*36*(1-I)}px) translateY(${18*(1-I)}px)`);set('.step-line',{transform:`scale${m?'Y':'X'}(${I})`});set('.door-left',{transform:`translateX(${-105*ease(b)}%)`});set('.door-right',{transform:`translateX(${105*ease(b)}%)`});

}

const defs=sections.map((el,i)=>({element:el,duration:i===0?4200:2800,render:p=>{sceneProgress.set(el,p);el.style.opacity=phase(p,0,.12);update();}}));return mountScenes(root,defs);
}
