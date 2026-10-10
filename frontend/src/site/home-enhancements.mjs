/** Additions own only new geometry variables and glow layers, never original transforms. */
export function measureHero(root) {
  const copy=root.querySelector('.hero-copy'),caption=root.querySelector('.hero-bottom');
  let disposed=false;
  const measure=()=>{
    if(disposed)return;
    const value=`${Math.ceil(copy.getBoundingClientRect().height+caption.getBoundingClientRect().height+56)}px`;
    if(root.style.getPropertyValue('--hero-content-height')!==value)root.style.setProperty('--hero-content-height',value);
  };
  measure();
  let observer;
  try{if(typeof ResizeObserver==='function'){observer=new ResizeObserver(measure);observer.observe(copy);observer.observe(caption);}}catch{observer?.disconnect();observer=null;}
  window.addEventListener('resize',measure);document.fonts?.ready?.then(measure);
  return()=>{disposed=true;observer?.disconnect();window.removeEventListener('resize',measure);root.style.removeProperty('--hero-content-height');};
}

export function mountCardAttention(root,{random=Math.random}={}) {
  const section=root.querySelector('#consultations'),cards=[...section.querySelectorAll('.service')];
  const layers=cards.map(card=>card.querySelector('.service-glow'));
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const eligible=new Set();
  let disposed=false,focusCard=null,hoverCard=null,active=null,animation=null,phase=0,timer=0,started=0,remaining=4000+random()*3000,last=null,bag=[],generation=0;
  let supported=typeof IntersectionObserver==='function'&&typeof MutationObserver==='function'&&layers.every(layer=>typeof layer.animate==='function');
  const manual=()=>focusCard??hoverCard;
  const ready=()=>section.dataset.motionProgress==='1.000';
  function pause(){
    if(timer){clearTimeout(timer);timer=0;remaining=Math.max(0,remaining-(performance.now()-started));}
    if(animation){phase=Number(animation.currentTime)||0;generation++;animation.cancel();animation=null;}
  }
  function paint(){layers.forEach((layer,i)=>{layer.style.opacity=cards[i]===manual()?'1':'0';});}
  function reset(){pause();active=null;phase=0;remaining=4000+random()*3000;}
  function choose(){
    if(!bag.some(card=>eligible.has(card)&&card!==last)){bag=[...eligible];for(let i=bag.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[bag[i],bag[j]]=[bag[j],bag[i]];}}
    const index=bag.findIndex(card=>eligible.has(card)&&card!==last);
    if(index===-1)return null;
    return bag.splice(index,1)[0];
  }
  function play(){
    const layer=layers[cards.indexOf(active)],token=++generation;
    try{animation=layer.animate([
      {opacity:0,offset:0,easing:'cubic-bezier(.2,.7,.2,1)'},
      {opacity:1,offset:600/1400},
      {opacity:1,offset:800/1400,easing:'cubic-bezier(.2,.7,.2,1)'},
      {opacity:0,offset:1},
    ],{duration:1400,fill:'none'});}catch{supported=false;reset();paint();return;}
    animation.currentTime=phase;
    animation.finished.then(()=>{
      if(disposed||token!==generation)return;
      animation=null;active=null;phase=0;remaining=4000+random()*3000;sync();
    }).catch(()=>{}); // Cancellation is expected on manual interaction, visibility and cleanup.
  }
  function sync(){
    if(disposed)return;
    if(active&&!eligible.has(active))reset();
    const blocked=!supported||reduced?.matches||document.hidden||manual()||!ready();
    if(blocked){pause();if(reduced?.matches){active=null;phase=0;}paint();return;}
    paint();
    if(active){if(!animation)play();return;}
    if(timer||![...eligible].some(card=>card!==last))return;
    started=performance.now();
    timer=setTimeout(()=>{
      timer=0;remaining=0;
      if(disposed||document.hidden||reduced?.matches||manual()||!ready()){sync();return;}
      active=choose();
      if(active){last=active;phase=0;play();}
    },remaining);
  }
  const cardFor=node=>{const card=node?.closest?.('.service');return cards.includes(card)?card:null;};
  const focusIn=event=>{focusCard=cardFor(event.target);sync();};
  const focusOut=event=>{focusCard=cardFor(event.relatedTarget);sync();};
  const over=event=>{if(event.pointerType==='touch')return;hoverCard=cardFor(event.target);sync();};
  const out=event=>{if(event.pointerType==='touch')return;hoverCard=cardFor(event.relatedTarget);sync();};
  section.addEventListener('focusin',focusIn);section.addEventListener('focusout',focusOut);
  section.addEventListener('pointerover',over);section.addEventListener('pointerout',out);
  const visibility=()=>sync();document.addEventListener('visibilitychange',visibility);reduced?.addEventListener?.('change',visibility);
  let intersection,progress;
  try{if(supported){
    intersection=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting&&entry.intersectionRatio>=.5)eligible.add(entry.target);else eligible.delete(entry.target);});sync();},{threshold:[0,.5,1]});
    cards.forEach(card=>intersection.observe(card));
    progress=new MutationObserver(sync);progress.observe(section,{attributes:true,attributeFilter:['data-motion-progress']});
  }}catch{supported=false;intersection?.disconnect();progress?.disconnect();}

  sync();
  return()=>{disposed=true;pause();intersection?.disconnect();progress?.disconnect();section.removeEventListener('focusin',focusIn);section.removeEventListener('focusout',focusOut);section.removeEventListener('pointerover',over);section.removeEventListener('pointerout',out);document.removeEventListener('visibilitychange',visibility);reduced?.removeEventListener?.('change',visibility);layers.forEach(layer=>layer.style.removeProperty('opacity'));};
}

export function mountHomeEnhancements(root){const stopSizing=measureHero(root),stopAttention=mountCardAttention(root);return()=>{stopSizing();stopAttention();};}

export function exclusiveFaq(event){
  const item=event.currentTarget;
  if(item.open)for(const sibling of item.parentElement.querySelectorAll('details[name="sarsa-home-faq"]'))if(sibling!==item&&sibling.open)sibling.open=false;
}
