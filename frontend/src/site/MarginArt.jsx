import {useLayoutEffect,useRef} from 'react';

/** Empty gutters are measured, never created by shrinking an existing scene. */
export function mountMarginArt(overlay,target,canvas){
  let disposed=false;
  const measure=()=>{
    if(disposed)return;
    if(!target?.isConnected||!canvas?.isConnected||innerWidth<=700){overlay.hidden=true;return;}
    const parent=overlay.offsetParent||overlay.parentElement;
    const p=parent.getBoundingClientRect(),r=canvas.getBoundingClientRect(),t=target.getBoundingClientRect();
    const margin=Math.min(r.left-p.left,p.right-r.right),size=Math.min(128,margin-72);
    overlay.hidden=size<96;
    if(overlay.hidden)return;
    overlay.style.setProperty('--margin-art-size',`${size}px`);
    overlay.style.top=`${t.top-p.top+r.height/2}px`;
    overlay.style.setProperty('--margin-art-inset',`${Math.max(24,(margin-size)/2)}px`);
  };
  measure();
  let resize;
  try{if(typeof ResizeObserver==='function'){resize=new ResizeObserver(measure);if(target)resize.observe(target);if(canvas&&canvas!==target)resize.observe(canvas);resize.observe(overlay.parentElement);}}catch{resize?.disconnect();resize=null;}
  let visible=false;
  const visibility=()=>{overlay.dataset.running=String(visible&&!document.hidden);};
  let intersection;
  try{if(typeof IntersectionObserver==='function'){intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;visibility();});if(target)intersection.observe(target);}}catch{intersection?.disconnect();intersection=null;}
  document.addEventListener('visibilitychange',visibility);window.addEventListener('resize',measure);document.fonts?.ready?.then(measure);
  return()=>{disposed=true;resize?.disconnect();intersection?.disconnect();document.removeEventListener('visibilitychange',visibility);window.removeEventListener('resize',measure);};
}
export default function MarginArt({targetId,canvasSelector}){
  const root=useRef(null);
  useLayoutEffect(()=>{const target=document.getElementById(targetId);return mountMarginArt(root.current,target,canvasSelector?target?.querySelector(canvasSelector):target);},[targetId,canvasSelector]);
  return <div ref={root} className="sarsa-margin-art" aria-hidden="true" hidden>{['left','right'].map(side=><svg key={side} className={side} viewBox="0 0 128 128"><circle cx="64" cy="64" r="54"/><circle cx="64" cy="64" r="39"/><path d="M64 10v108M10 64h108M26 26l76 76M102 26l-76 76M64 25l39 39-39 39-39-39Z"/><circle cx="64" cy="64" r="7"/></svg>)}</div>;
}
