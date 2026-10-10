import {useLayoutEffect,useRef} from 'react';

/** A single button stays in its footer slot; floating is only a presentation state. */
export function mountBackToTop(slot,button){
  let frame=0,disposed=false,inline=true;
  const main=document.getElementById('page-content');
  let obstacles=[];
  const collect=()=>{obstacles=[...main.querySelectorAll('h1,h2,h3,p,a,button,summary,.shared-disc,.about-image,.faq-title')];};
  collect();
  let changes;
  try{if(typeof MutationObserver==='function'){changes=new MutationObserver(()=>{collect();schedule();});changes.observe(main,{childList:true,subtree:true});}}catch{changes?.disconnect();changes=null;}
  function update(){
    frame=0;if(disposed)return;
    button.dataset.placement=inline?'inline':'floating';
    let show=inline||window.scrollY>=window.innerHeight;
    if(show&&!inline){
      const style=getComputedStyle(button),size=slot.getBoundingClientRect().width;
      const right=parseFloat(style.right)||0,bottom=parseFloat(style.bottom)||0;
      const box={left:innerWidth-right-size-8,right:innerWidth-right+8,top:innerHeight-bottom-size-8,bottom:innerHeight-bottom+8};
      show=!obstacles.some(el=>{
        if(!el.isConnected||!el.getClientRects().length)return false;
        const r=el.getBoundingClientRect();
        return r.width>0&&r.height>0&&r.bottom>box.top&&r.top<box.bottom&&r.right>box.left&&r.left<box.right;
      });
    }
    if(!show&&document.activeElement===button)main.focus({preventScroll:true});
    button.hidden=!show;
  }
  function schedule(){if(!frame&&!disposed){if(typeof requestAnimationFrame==='function')frame=requestAnimationFrame(update);else update();}}
  let observer;
  try{if(typeof IntersectionObserver==='function'){observer=new IntersectionObserver(entries=>{inline=entries[0].isIntersecting;schedule();});observer.observe(slot.closest('footer'));}}catch{observer?.disconnect();observer=null;}
  const toggle=()=>{collect();schedule();};
  window.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);
  main.addEventListener('toggle',toggle,true);
  update();
  return()=>{disposed=true;if(frame)cancelAnimationFrame(frame);observer?.disconnect();changes?.disconnect();window.removeEventListener('scroll',schedule);window.removeEventListener('resize',schedule);main.removeEventListener('toggle',toggle,true);};
}
export default function BackToTop({scrollerRef}){
  const slot=useRef(null),button=useRef(null);
  useLayoutEffect(()=>mountBackToTop(slot.current,button.current),[]);
  return <div className="sarsa-top-slot" ref={slot}><button type="button" ref={button} className="sarsa-top" aria-label="Back to top" onClick={event=>scrollerRef.current?.top(event.detail===0)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 13l6-6 6 6M12 7v13M5 3h14"/></svg></button></div>;
}
