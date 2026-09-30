/* Distinct, deterministic timelines for the six reviewed sections. */
const clamp=n=>Math.max(0,Math.min(1,n));
const phase=(p,a,b)=>{const q=clamp((p-a)/(b-a));return q*q*(3-2*q)};
const transform=(el,value)=>{if(el)el.style.transform=value};
const opacity=(el,value)=>{if(el)el.style.opacity=value};
export function renderBookingScene(section,p){
 const find=s=>section.querySelector(s),all=s=>section.querySelectorAll(s),mobile=innerWidth<=650;
 if(section.id==='welcome'){
  const a=phase(p,0,.38),b=phase(p,.24,.73),c=phase(p,.62,1);
  transform(find('.cover-left'),`translateX(${-20*a}px) rotateY(${-120*a}deg)`);
  transform(find('.cover-right'),`translateX(${20*a}px) rotateY(${120*a}deg)`);
  all('.folio-cover').forEach(el=>opacity(el,1-phase(p,.24,.48)));
  transform(find('.folio-paper'),`translateX(${(mobile?24:48)*(1-b)}px) rotate(${5*(1-b)}deg)`);
  transform(find('.folio-rule'),`scaleX(${b})`);
  transform(find('.invitation-tab'),`translateY(${42*(1-c)}px) rotate(${-10*(1-c)}deg)`);opacity(find('.invitation-tab'),c);
  transform(find('.hero-foot .fine-line'),`scaleX(${c})`);
 }else if(section.id==='service'){
  transform(find('.shelf-rail'),`scaleX(${phase(p,0,.3)})`);
  all('.service-card').forEach((el,i)=>{const q=phase(p,.12+i*.06,.65+i*.07);transform(el,`translate(${(mobile?0:(i%2?18:-18))*(1-q)}px,${(18+i*4)*(1-q)}px) rotate(${(mobile?0:(i%2?1:-1))*2*(1-q)}deg)`);opacity(el,q)});
 }else if(section.id==='appointment'){
  const a=phase(p,0,.32),b=phase(p,.15,.64);
  transform(find('.window-frame'),`scale(${.83+.17*a})`);
  transform(find('.window-shutter'),`translateX(${110*b}%)`);
  all('.slot-option').forEach((el,i)=>{const q=phase(p,.48+i*.05,.8+i*.05);transform(el,`translateX(${(i%2?1:-1)*(mobile?14:25)*(1-q)}px)`);opacity(el,q)});
  transform(find('.date-rail'),`translateY(${14*(1-phase(p,.4,.77))}px)`);opacity(find('.date-rail'),phase(p,.4,.77));
  transform(find('.appointment-mark'),`rotate(${-35*(1-a)}deg)`);
 }else if(section.id==='details'){
  const a=phase(p,0,.4),b=phase(p,.28,.76),c=phase(p,.57,1);
  transform(find('.context-sheet'),`scaleX(${.94+.06*a})`);
  all('.context-sheet .field').forEach((el,i)=>{const q=phase(p,.2+i*.07,.62+i*.07);transform(el,`translateY(${14*(1-q)}px)`);opacity(el,q)});
  transform(find('.context-recap'),`translate(${(mobile?0:30)*(1-c)}px,${(mobile?14:0)*(1-c)}px) rotate(${(mobile?0:3)*(1-c)}deg)`);opacity(find('.context-recap'),c);
  transform(find('.recap-line'),`scaleX(${c})`);transform(find('.sheet-topline'),`translateY(${10*(1-b)}px)`);
 }else if(section.id==='review'){
  all('.summary-row').forEach((el,i)=>{const q=phase(p,i*.09,.48+i*.09);transform(el,`translateX(${(i%2?1:-1)*25*(1-q)}px)`);opacity(el,q)});
  transform(find('.amount-plaque'),`translateY(${12*(1-phase(p,.52,.82))}px)`);opacity(find('.amount-plaque'),phase(p,.52,.82));
  transform(find('.summary-seam'),`scaleY(${phase(p,.38,.79)})`);
  // Action bounds stay fixed, including during the first pointer click.
  transform(find('.review-bottom'),'none');opacity(find('.review-bottom'),phase(p,.55,1));
 }else if(section.id==='questions'){
  all('.question-index').forEach((el,i)=>{const q=phase(p,i*.12,.5+i*.12);transform(el,`translateY(${12*(1-q)}px)`);opacity(el,q)});
  all('.question-list details').forEach((el,i)=>el.style.borderBottomColor=`rgba(121,145,101,${phase(p,.25+i*.09,.65+i*.09)*.5})`);
  transform(find('.folded-link span'),`translateY(${8*(1-phase(p,.65,1))}px)`);
 }
}

export function mountBookingMotion(root) {
 const sections=[...root.querySelectorAll('.story-section')], media=matchMedia('(prefers-reduced-motion: reduce)');
 const durations={welcome:3800,service:2300,appointment:2600,details:2100,review:2200,questions:1800};
 const frames=new Map(), played=new Set();
 function settle(section){const frame=frames.get(section);if(frame)cancelAnimationFrame(frame);frames.delete(section);played.add(section);renderBookingScene(section,1)}
 function play(section){if(played.has(section))return;played.add(section);const start=performance.now();
  const tick=now=>{const p=Math.min(1,(now-start)/(durations[section.id]||1800));renderBookingScene(section,p);
   if(p<1)frames.set(section,requestAnimationFrame(tick));else frames.delete(section)};
  frames.set(section,requestAnimationFrame(tick));}
 sections.forEach(section=>renderBookingScene(section,media.matches?1:0));
 const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){play(entry.target);observer.unobserve(entry.target)}},{threshold:.12});
 if(media.matches)sections.forEach(settle);else {sections.forEach(section=>section.id==='welcome'?play(section):observer.observe(section))}
 let pointerActive=false;
 const targetSection=e=>e.target.closest('input,textarea,select,button,a,label,summary')?e.target.closest('.story-section'):null;
 const freeze=e=>{pointerActive=true;const section=targetSection(e);if(section){const frame=frames.get(section);if(frame)cancelAnimationFrame(frame);frames.delete(section);played.add(section)}};
 const interact=e=>{const section=targetSection(e);if(section&&(e.type==='click'||!pointerActive))settle(section);if(e.type==='click')pointerActive=false};
 const release=()=>{pointerActive=false};
 const reduce=()=>{if(media.matches){observer.disconnect();sections.forEach(settle)}};
 root.addEventListener('pointerdown',freeze);root.addEventListener('click',interact);root.addEventListener('focusin',interact);root.addEventListener('pointercancel',release);root.addEventListener('pointerup',release);media.addEventListener('change',reduce);
 return()=>{observer.disconnect();frames.forEach(cancelAnimationFrame);root.removeEventListener('pointerdown',freeze);root.removeEventListener('click',interact);root.removeEventListener('focusin',interact);root.removeEventListener('pointercancel',release);root.removeEventListener('pointerup',release);media.removeEventListener('change',reduce)};
}
