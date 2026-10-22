const portraitFrames=new WeakMap();
export const portraitFrameFor=root=>portraitFrames.get(root);
/** The original About backdrops use the page root as their containing block.
 * Keep their original bounds when service actions and the fifth service
 * add normal-flow height. Original movement formulas stay unchanged. */
export function mountAboutLayout(root){
 const scene=root.querySelector('#scene'),list=root.querySelector('.service-list'),intro=root.querySelector('.consultation-grid>div'),band=root.querySelector('[data-hero-band]');
 const variables=[['--about-row-growth',1],['--about-row-growth-60',.6],['--about-row-growth-56',.56]];
 const bandVariables=[['--about-hero-band-growth',1],['--about-hero-band-growth-40',.4],['--about-hero-band-growth-44',.44]];
 let disposed=false,observer;
 const measure=()=>{
  if(disposed)return;
  if(scene)portraitFrames.set(root,{width:scene.clientWidth,height:scene.clientHeight});
  const rows=[...list.querySelectorAll('.service-row')];
  const identityHeight=rows.filter(row=>['kundli-prediction','kundli-matching','vastu-consultation','numerology'].includes(row.dataset.serviceId)).reduce((sum,row)=>{
   const actions=row.querySelector('.row-actions'),style=getComputedStyle(actions);
   const added=style.position==='absolute'?0:actions.getBoundingClientRect().height+(parseFloat(style.marginTop)||0);
   return sum+row.getBoundingClientRect().height-added;
  },0);
  const naturalIntro=Math.max(0,intro.lastElementChild.getBoundingClientRect().bottom-intro.getBoundingClientRect().top);
  const growth=Math.max(0,list.getBoundingClientRect().height-Math.max(identityHeight,naturalIntro));
  for(const [name,factor] of variables){
   const value=(growth*factor)+'px';if(root.style.getPropertyValue(name)!==value)root.style.setProperty(name,value);
  }
  // offsetHeight measures normal-flow space, without the entry/hover transforms.
  for(const [name,factor] of bandVariables){
   const value=((band?.offsetHeight||0)*factor)+'px';if(root.style.getPropertyValue(name)!==value)root.style.setProperty(name,value);
  }
 };
 measure();
 try{if(typeof ResizeObserver==='function'){observer=new ResizeObserver(measure);[root,list,intro,band,scene].filter(Boolean).forEach(e=>observer.observe(e));}}catch{observer?.disconnect();observer=null;}
 window.addEventListener('resize',measure);document.fonts?.ready?.then(measure);
 return()=>{disposed=true;portraitFrames.delete(root);observer?.disconnect();window.removeEventListener('resize',measure);[...variables,...bandVariables].forEach(([name])=>root.style.removeProperty(name));};
}
