/** Scene transforms live on parents; mode crossfades live on their SVG children. */
const phase=(p,a,b)=>{const t=Math.max(0,Math.min(1,(p-a)/(b-a)));return t*t*(3-2*t);};
export function createVastuPrinciplesScene(root){
 const element=root.querySelector('[data-service-scene=principles]');
 if(!element)return [];
 const stages=[...element.querySelectorAll('[data-principles-stage]')];
 const lines=[...element.querySelectorAll('[data-grid-line]')];
 return [{element,duration:2600,render:p=>{
  const timings=[[0,700],[350,1500],[900,2200],[1500,2600]];
  stages.forEach((layer,index)=>{
   const [start,end]=timings[index],t=phase(p,start/2600,end/2600);
   Object.assign(layer.style,{opacity:t,transform:`translateY(${(index===0?14:8)*(1-t)}px) scale(${.98+.02*t})`});
  });
  lines.forEach((line,index)=>{
   const t=phase(p,(350+index*25)/2600,(950+index*25)/2600);
   Object.assign(line.style,{opacity:t,transform:line.dataset.gridLine==='column'?`scaleY(${t})`:`scaleX(${t})`});
  });
 }}];
}
