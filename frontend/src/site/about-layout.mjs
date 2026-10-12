/** The original About backdrops use the page root as their containing block.
 * Keep their original bounds when service actions and the certificate section
 * add normal-flow height. Original movement formulas stay unchanged. */
export function mountAboutLayout(root){
 const list=root.querySelector('.service-list'),intro=root.querySelector('.consultation-grid>div'),certificates=root.querySelector('.sarsa-certifications');
 let disposed=false,observer;
 const measure=()=>{
  if(disposed)return;
  const rows=[...list.querySelectorAll('.service-row')];
  const identityHeight=rows.reduce((sum,row)=>{
   const actions=row.querySelector('.row-actions'),style=getComputedStyle(actions);
   const added=style.position==='absolute'?0:actions.getBoundingClientRect().height+(parseFloat(style.marginTop)||0);
   return sum+row.getBoundingClientRect().height-added;
  },0);
  const naturalIntro=Math.max(0,intro.lastElementChild.getBoundingClientRect().bottom-intro.getBoundingClientRect().top);
  const growth=Math.max(0,list.getBoundingClientRect().height-Math.max(identityHeight,naturalIntro))+(certificates?.getBoundingClientRect().height||0);
  for(const [name,factor] of [['--about-row-growth',1],['--about-row-growth-60',.6],['--about-row-growth-56',.56]]){
   const value=(growth*factor)+'px';if(root.style.getPropertyValue(name)!==value)root.style.setProperty(name,value);
  }
 };
 measure();
 try{if(typeof ResizeObserver==='function'){observer=new ResizeObserver(measure);[root,list,intro,certificates].filter(Boolean).forEach(e=>observer.observe(e));}}catch{observer?.disconnect();observer=null;}
 window.addEventListener('resize',measure);document.fonts?.ready?.then(measure);
 return()=>{disposed=true;observer?.disconnect();window.removeEventListener('resize',measure);['--about-row-growth','--about-row-growth-60','--about-row-growth-56'].forEach(name=>root.style.removeProperty(name));};
}
