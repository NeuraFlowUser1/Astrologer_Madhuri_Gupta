/** Two finite, distinct card highlights. No timer runs after interruption. */
export function watchCardAttention(root,{played,rng=Math.random}={}){
 if(!root||typeof IntersectionObserver!=='function')return()=>{};
 const preference=matchMedia('(prefers-reduced-motion: reduce)'),cards=[...root.querySelectorAll('.service-card')];
 let observer,timers=[],current=null,disposed=false;
 function stop(){timers.forEach(clearTimeout);timers=[];current?.classList.remove('pulse');current=null;observer?.disconnect();}
 function interrupted(){played.current=true;stop();}
 const visibility=()=>{if(document.hidden)interrupted();};
 const changed=()=>{if(preference.matches)interrupted();};
 function play(){
  if(disposed||played.current||preference.matches||document.hidden||!cards.length)return;
  played.current=true;observer?.disconnect();
  const first=Math.floor(rng()*cards.length)%cards.length;
  const remaining=cards.filter((_,i)=>i!==first),second=remaining.length?remaining[Math.floor(rng()*remaining.length)%remaining.length]:null;
  current=cards[first];current.classList.add('pulse');
  timers.push(setTimeout(()=>{current.classList.remove('pulse');current=null;},900));
  if(second)timers.push(setTimeout(()=>{current=second;current.classList.add('pulse');timers.push(setTimeout(()=>{current.classList.remove('pulse');current=null;},900));},1140));
 }
 if(preference.matches||document.hidden)played.current=true;
 else if(!played.current){try{observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))play();},{threshold:.2});observer.observe(root);}catch{played.current=true;stop();return()=>{};}}
 root.addEventListener('pointerdown',interrupted);root.addEventListener('focusin',interrupted);document.addEventListener('visibilitychange',visibility);preference.addEventListener('change',changed);
 return()=>{disposed=true;stop();root.removeEventListener('pointerdown',interrupted);root.removeEventListener('focusin',interrupted);document.removeEventListener('visibilitychange',visibility);preference.removeEventListener('change',changed);};
}
