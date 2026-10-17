/** Observe the existing scene clock. No second timeline or original transform owner. */
export function mountHeroBand(root,sceneSelector){
 const scene=root.querySelector(sceneSelector),band=root.querySelector('[data-hero-band]');
 let disposed=false;
 const paint=()=>{
  if(disposed)return;
  const progress=Number(scene.dataset.motionProgress??1);
  const t=Math.max(0,Math.min(1,(progress-.78)/.22));
  band.style.opacity=String(t*t*(3-2*t));
 };
 paint();
 if(typeof MutationObserver!=='function'){band.style.opacity='1';return()=>band.style.removeProperty('opacity');}
 const observer=new MutationObserver(paint);
 observer.observe(scene,{attributes:true,attributeFilter:['data-motion-progress']});
 return()=>{disposed=true;observer.disconnect();band.style.removeProperty('opacity');};
}
