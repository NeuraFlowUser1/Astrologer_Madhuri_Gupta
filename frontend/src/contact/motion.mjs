/* Client-original Contact geometry adapted from approved storyboard13. */
const clamp=n=>Math.max(0,Math.min(1,n));
const phase=(p,a,b)=>{const t=clamp((p-a)/(b-a));return t*t*(3-2*t)};
const transform=(el,value)=>{if(el)el.style.transform=value};
const opacity=(el,value)=>{if(el)el.style.opacity=value};
export function renderContactScene(stage, progress) {
  const find = selector => stage.querySelector(selector);
  const all = selector => [...stage.querySelectorAll(selector)];
  const mobile = innerWidth <= 650;
  if (stage.id === 'scene-listening') {
    stage.style.setProperty('--hero-art-opacity', clamp(progress / .12));
    const align = phase(progress, 0, .292), open = phase(progress, .194, .653), reply = phase(progress, .528, 1);
    transform(find('.rim-left'), `translateX(${-50 * (1 - align)}px) rotate(${-28 * (1 - align)}deg) scale(${1 - .08 * open})`);
    transform(find('.rim-right'), `translateX(${50 * (1 - align)}px) rotate(${28 * (1 - align)}deg) scale(${1 - .08 * open})`);
    transform(find('.portal-plane'), `scale(${.25 + .75 * open})`);
    opacity(find('.portal-plane'), open);
    transform(find('.fragment-question'), `translate(${-55 * (1 - reply)}px,${20 * (1 - reply)}px) rotate(${-8 + 5 * reply}deg)`);
    transform(find('.fragment-reply'), `translate(${35 * (1 - reply)}px,${35 * (1 - reply)}px) rotate(${7 - 4 * reply}deg)`);
    all('.correspondence-fragment').forEach(element => opacity(element, reply));
    opacity(find('.ground-shadow'), open);
  } else if (stage.id === 'scene-routes') {
    const travel = phase(progress, 0, .241), branch = phase(progress, .167, .574);
    transform(find('.junction-line'), `scale${mobile ? 'Y' : 'X'}(${branch})`);
    const chosen = ['question','booking','existing'].indexOf(stage.querySelector('[data-route][data-selected=true]')?.dataset.route || 'question');
    const marker = find('.junction-marker');
    const junction = find('.route-junction'), lane = all('.route-lane')[chosen];
    const startX = junction.clientWidth * .08;
    const targetX = lane.offsetLeft + lane.offsetWidth / 2;
    marker.style.left = mobile ? '-5px' : `${startX + (targetX - startX) * travel - 5}px`;
    marker.style.top = mobile ? `${8 + (lane.offsetTop + 45 - 8) * travel - 5}px` : '-5px';
    all('.branch').forEach(element => transform(element, `scale${mobile ? 'X' : 'Y'}(${branch})`));
    all('.route-lane').forEach((element, index) => {
      const join = phase(progress, .426 + index * .025, .9 + index * .05);
      transform(element, `translateY(${18 * (1 - join)}px) rotate(${(mobile ? 0 : index - 1) * 4 * (1 - join)}deg)`);
      opacity(element, join);
    });
  } else if (stage.id === 'scene-desk') {
    const spine = phase(progress, 0, .26), paper = phase(progress, .16, .58), margin = phase(progress, .44, 1);
    transform(find('.desk-spine'), `translateX(${-12 * (1 - spine)}px) scaleY(${spine})`);
    find('.message-sheet').style.clipPath = paper === 1 ? 'none' : `inset(0 ${100 * (1 - paper)}% 0 0 round 22px)`;
    transform(find('.sheet-heading'), `translateY(${8 * (1 - paper)}px)`);
    transform(find('.reply-tab'), `rotateX(${-85 * (1 - margin)}deg) translateY(${16 * (1 - margin)}px)`);
    transform(find('.margin-rule'), `scaleX(${margin})`);
    all('.field').forEach((element, index) => opacity(element, phase(progress, .44 + index * .04, .8 + index * .04)));
  } else if (stage.id === 'scene-answers') {
    const bind = phase(progress, 0, .239);
    transform(find('.answer-binding'), `scaleY(${bind})`);
    all('.answer-leaf').forEach((element, index) => {
      const gather = phase(progress, .152 + index * .04, .55 + index * .034);
      transform(element, `translateX(${(mobile ? 12 : 24 + index * 6) * (1 - gather)}px) rotate(${(mobile ? 0 : 1 + index * .6) * (1 - gather)}deg)`);
      opacity(element, gather);
    });
    all('.leaf-index').forEach((element, index) => transform(element, `rotateY(${75 * (1 - phase(progress, .543 + index * .035, .895 + index * .035))}deg)`));
  } else if (stage.id === 'scene-weave') {
    all('.weave-band').forEach((element, index) => {
      const lay = phase(progress, index * .045, .286 + index * .04);
      transform(element, `translateX(${(index % 2 ? 1 : -1) * 70 * (1 - lay)}px)`); opacity(element, lay);
    });
    all('.weave-vertical').forEach((element, index) => {
      const weave = phase(progress, .196 + index * .045, .571 + index * .045);
      transform(element, `translateY(${35 * (1 - weave)}px) rotateX(${25 * (1 - weave)}deg)`); opacity(element, weave);
    });
    const invite = phase(progress, .571, 1);
    transform(find('.weave-plaque'), `translateY(${12 * (1 - invite)}px) rotateY(${-10 * (1 - invite)}deg) scale(${.96 + .04 * invite})`);
    opacity(find('.weave-plaque'), invite);
  }
}

export function mountContactMotion(root){
 const sections=[...root.querySelectorAll('.stage')],media=matchMedia('(prefers-reduced-motion: reduce)');
 const durations=[3600,2700,2500,2300,2800],frames=new Map(),played=new Set(),visible=new Map();
 let ambient=true;
 root.classList.add('motion-ready');
 function sync(){
  const reduced=media.matches;root.classList.toggle('motion-off',reduced||!ambient);
  sections.forEach(s=>s.classList.toggle('ambient-live',ambient&&!reduced&&!document.hidden&&visible.get(s)&&s.dataset.motionProgress==='1'));
  const control=root.querySelector('[data-motion]');
  if(control){control.textContent=reduced?'Reduced motion':ambient?'Pause background movement':'Resume background movement';control.disabled=reduced;control.setAttribute('aria-pressed',String(ambient&&!reduced));}
 }
 function render(section,p){section.style.opacity=String(clamp(p/.12));section.dataset.motionProgress=String(p);renderContactScene(section,p);if(p===1)sync();}
 function settle(section){cancelAnimationFrame(frames.get(section));frames.delete(section);played.add(section);render(section,1);}
 function play(section){if(played.has(section))return;played.add(section);const start=performance.now(),duration=durations[sections.indexOf(section)];
  const tick=time=>{const p=Math.min(1,(time-start)/duration);render(section,p);if(p<1)frames.set(section,requestAnimationFrame(tick));else frames.delete(section);};frames.set(section,requestAnimationFrame(tick));}
 sections.forEach(s=>render(s,media.matches?1:0));
 const entry=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){play(e.target);entry.unobserve(e.target);}},{rootMargin:'0px 0px -18% 0px',threshold:.05});
 const light=new IntersectionObserver(entries=>{entries.forEach(e=>visible.set(e.target,e.isIntersecting));sync();});
 sections.forEach((s,i)=>{light.observe(s);if(media.matches)settle(s);else if(i===0)play(s);else entry.observe(s);});
 let pointerActive=false,pointerSection=null,releaseFrame=null;
 const freeze=e=>{if(e.target.closest('input,textarea,select,button,a,summary')){pointerActive=true;const s=e.target.closest('.stage');pointerSection=s;if(s){cancelAnimationFrame(frames.get(s));frames.delete(s);}}};
 const focus=e=>{if(!pointerActive&&e.target.closest('input,textarea,select,button,a,summary,[tabindex]')){const s=e.target.closest('.stage');if(s)settle(s);}};
 const release=e=>{pointerActive=false;cancelAnimationFrame(releaseFrame);const s=pointerSection||e.target.closest('.stage');pointerSection=null;if(s)settle(s);};
 const pointerUp=e=>{pointerActive=false;releaseFrame=requestAnimationFrame(()=>release(e));};
 const click=e=>{release(e);if(e.target.closest('[data-motion]')){ambient=!ambient;if(!ambient)sections.forEach(settle);sync();}};
 const reduce=()=>{if(media.matches){entry.disconnect();sections.forEach(settle);}sync();};
 const resize=()=>sections.forEach(s=>renderContactScene(s,Number(s.dataset.motionProgress)||0));
 root.addEventListener('focusin',focus);root.addEventListener('pointerdown',freeze);document.addEventListener('pointercancel',release);document.addEventListener('pointerup',pointerUp);root.addEventListener('click',click);
 media.addEventListener('change',reduce);document.addEventListener('visibilitychange',sync);window.addEventListener('resize',resize);sync();
 return()=>{entry.disconnect();light.disconnect();frames.forEach(cancelAnimationFrame);root.removeEventListener('focusin',focus);root.removeEventListener('pointerdown',freeze);document.removeEventListener('pointercancel',release);document.removeEventListener('pointerup',pointerUp);cancelAnimationFrame(releaseFrame);root.removeEventListener('click',click);media.removeEventListener('change',reduce);document.removeEventListener('visibilitychange',sync);window.removeEventListener('resize',resize);};
}
