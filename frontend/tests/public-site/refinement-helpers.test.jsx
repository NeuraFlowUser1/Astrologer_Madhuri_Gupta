import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {observeHeader,createPublicScroller,scrollEase} from '../../src/site/public-scroll.mjs';
import {measureHero,mountCardAttention,mountHomeEnhancements,exclusiveFaq} from '../../src/site/home-enhancements.mjs';
import {mountMarginArt} from '../../src/site/MarginArt.jsx';
import {mountBackToTop} from '../../src/site/BackToTop.jsx';
import {mountAboutLayout} from '../../src/site/about-layout.mjs';
let media,intersections,resizes,frames,clock,animations;
const rect=(left=0,top=0,width=200,height=100)=>({left,top,width,height,x:left,y:top,right:left+width,bottom:top+height});
const tick=now=>{clock=now;const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(now));};
const el=(html)=>{const root=document.createElement('div');root.innerHTML=html;document.body.append(root);return root;};
beforeEach(()=>{
 vi.useFakeTimers();clock=0;vi.spyOn(performance,'now').mockImplementation(()=>clock);
 frames=new Map();let id=0;vi.stubGlobal('requestAnimationFrame',fn=>{frames.set(++id,fn);return id;});vi.stubGlobal('cancelAnimationFrame',key=>frames.delete(key));
 media=new EventTarget();media.matches=false;vi.stubGlobal('matchMedia',()=>media);
 intersections=[];resizes=[];animations=[];
 vi.stubGlobal('IntersectionObserver',class{constructor(fn){this.fn=fn;this.observe=vi.fn();this.disconnect=vi.fn();intersections.push(this);}});
 vi.stubGlobal('ResizeObserver',class{constructor(fn){this.fn=fn;this.observe=vi.fn();this.disconnect=vi.fn();resizes.push(this);}});
 Object.defineProperty(document,'fonts',{value:{ready:Promise.resolve()},configurable:true});
 Object.defineProperty(document,'hidden',{value:false,writable:true,configurable:true});
 for(const [name,value] of Object.entries({innerWidth:1440,innerHeight:900,scrollY:100}))Object.defineProperty(window,name,{value,writable:true,configurable:true});
 Object.defineProperty(document.documentElement,'scrollHeight',{value:5000,configurable:true});window.scrollTo=vi.fn();
 vi.stubGlobal('Animation',class{});
 Element.prototype.animate=vi.fn(function(){let resolve,reject;const finished=new Promise((a,b)=>{resolve=a;reject=b;});const animation={element:this,currentTime:0,finished,cancel:vi.fn(()=>reject(Error('cancelled'))),complete:resolve};animations.push(animation);return animation;});
});
afterEach(()=>{document.body.replaceChildren();delete Element.prototype.animate;delete document.fonts;vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});

test('header and hero measurements update only their variables, handle missing observation and ignore disposed callbacks',async()=>{
 const shell=el('<header></header><div class="hero-copy"></div><div class="hero-bottom"></div>');const header=shell.querySelector('header');let height=85;header.getBoundingClientRect=()=>rect(0,0,400,height);
 const stop=observeHeader(shell,header);expect(shell.style.getPropertyValue('--public-header-height')).toBe('85px');resizes[0].fn();height=135;window.dispatchEvent(new Event('resize'));expect(shell.style.getPropertyValue('--public-header-height')).toBe('135px');stop();height=200;resizes[0].fn();expect(shell.style.getPropertyValue('--public-header-height')).toBe('135px');
 shell.querySelector('.hero-copy').getBoundingClientRect=()=>rect(0,0,400,360);shell.querySelector('.hero-bottom').getBoundingClientRect=()=>rect(0,0,400,32);
 const end=measureHero(shell);expect(shell.style.getPropertyValue('--hero-content-height')).toBe('448px');resizes[1].fn();end();resizes[1].fn();expect(shell.style.getPropertyValue('--hero-content-height')).toBe('');
 vi.stubGlobal('ResizeObserver',undefined);const fallback=observeHeader(shell,header),heroFallback=measureHero(shell);await Promise.resolve();header.remove();window.dispatchEvent(new Event('resize'));fallback();heroFallback();
 vi.stubGlobal('ResizeObserver',class{constructor(){throw Error('unsupported');}});const a=observeHeader(shell,header),b=measureHero(shell);a();b();
});

function scrollFixture(){
 const root=el('<header style="position:sticky"></header><main id="page-content" tabindex="-1"><a href="#destination" data-public-scroll>Discover</a><span tabindex="-1" data-scroll-destination="destination">Destination</span><section id="destination"><h2>Destination</h2></section><input></main>');
 const main=root.querySelector('main'),header=root.querySelector('header');header.getBoundingClientRect=()=>rect(0,0,1440,85);main.querySelector('section').getBoundingClientRect=()=>rect(0,800,1000,400);
 const navigate=vi.fn(),owner=createPublicScroller({main,header,navigate});return {root,main,header,navigate,owner,link:main.querySelector('a'),marker:main.querySelector('span')};
}
test('one activated scroll eases for 400ms, uses the real sticky header and focuses only the outside marker',()=>{
 const f=scrollFixture();f.owner.route({pathname:'/',search:'',hash:'',key:'initial'},'POP');expect(window.scrollTo).toHaveBeenLastCalledWith(0,0);window.scrollTo.mockClear();
 f.link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,detail:0}));expect(f.navigate).toHaveBeenCalledOnce();f.owner.route({pathname:'/',search:'',hash:'#destination',key:'a'},'PUSH');expect(frames.size).toBe(1);tick(200);expect(window.scrollTo.mock.calls[0][1]).toBeGreaterThan(500);expect(document.activeElement).not.toBe(f.marker);tick(400);expect(window.scrollTo).toHaveBeenLastCalledWith(0,799);expect(document.activeElement).toBe(f.marker);
 f.link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,detail:1}));f.owner.route({pathname:'/',search:'',hash:'#destination',key:'b'},'PUSH');tick(800);expect(f.navigate).toHaveBeenCalledTimes(2);f.owner.dispose();
 expect(scrollEase(0)).toBe(0);expect(scrollEase(1)).toBe(1);expect(scrollEase(-1)).toBe(0);expect(scrollEase(2)).toBe(1);
});
test.each(['wheel','touchstart','pointerdown','resize','keydown','hidden','preference','navigation'])('public scroll yields to %s and never completes stale focus',kind=>{
 const f=scrollFixture();f.owner.top(true);tick(100);window.scrollTo.mockClear();
 if(kind==='hidden'){document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));}
 else if(kind==='preference')media.dispatchEvent(new Event('change'));
 else if(kind==='navigation')f.owner.route({pathname:'/about',search:'',hash:'#missing'},'POP');
 else window.dispatchEvent(kind==='keydown'?new KeyboardEvent('keydown',{key:'PageDown'}):new Event(kind));
 tick(500);expect(window.scrollTo).not.toHaveBeenCalled();expect(document.activeElement).not.toBe(f.main);f.owner.dispose();
});
test('typing and unrelated keys do not cancel; reduced motion, static headers and unavailable frames position instantly',()=>{
 const f=scrollFixture();f.owner.top(true);f.main.querySelector('input').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'}));document.dispatchEvent(new Event('visibilitychange'));tick(400);expect(document.activeElement).toBe(f.main);
 media.matches=true;f.header.style.position='static';f.owner.route({pathname:'/',search:'',hash:'#destination'},'POP');expect(window.scrollTo).toHaveBeenLastCalledWith(0,900);
 window.scrollTo.mockClear();f.owner.route({pathname:'/',search:'?service=x',hash:'#destination'},'PUSH');expect(window.scrollTo).not.toHaveBeenCalled();
 media.matches=false;vi.stubGlobal('requestAnimationFrame',undefined);f.owner.top(false);expect(window.scrollTo).toHaveBeenLastCalledWith(0,0);f.owner.dispose();
});
test('lazy hash waits are bounded, scoped, cancelled on navigation and tolerate invalid or outside destinations',async()=>{
 const f=scrollFixture();f.owner.route({pathname:'/',search:'',hash:'#%ZZ'},'POP');expect(window.scrollTo).not.toHaveBeenCalled();
 f.owner.route({pathname:'/',search:'',hash:'#late'},'POP');const target=document.createElement('section');target.id='late';target.getBoundingClientRect=()=>rect(0,700,400,200);f.main.append(target);await Promise.resolve();expect(window.scrollTo).toHaveBeenLastCalledWith(0,715);
 window.scrollTo.mockClear();f.owner.route({pathname:'/',search:'',hash:'#never'},'POP');vi.advanceTimersByTime(10001);const outside=document.createElement('div');outside.id='never';document.body.append(outside);await Promise.resolve();expect(window.scrollTo).not.toHaveBeenCalled();
 f.owner.route({pathname:'/',search:'',hash:'#outside'},'POP');outside.id='outside';await Promise.resolve();expect(window.scrollTo).not.toHaveBeenCalled();f.owner.dispose();
 vi.stubGlobal('MutationObserver',undefined);const second=scrollFixture();second.owner.route({pathname:'/',search:'',hash:'#missing'},'POP');second.owner.dispose();
});
test.each([{ctrlKey:true},{metaKey:true},{altKey:true},{shiftKey:true},{button:1},{href:'/about#destination'},{href:'/?q=x#destination'},{href:'https://example.invalid/#destination'},{href:'/'},{target:'_blank'},{download:'copy'}])('declared anchors retain browser behaviour for %j',options=>{
 const f=scrollFixture();for(const key of ['href','target','download'])if(key in options)f.link.setAttribute(key,options[key]);
 const event=new MouseEvent('click',{bubbles:true,cancelable:true,...options});f.link.dispatchEvent(event);expect(f.navigate).not.toHaveBeenCalled();f.owner.dispose();
});

function attentionFixture(){const root=el('<div class="hero-copy"></div><div class="hero-bottom"></div><section id="consultations" data-motion-progress="1.000">'+Array.from({length:4},(_,i)=>`<article class="service" data-card="${i}"><div class="service-glow"></div><a href="#">Explore</a></article>`).join('')+'</section>');return {root,cards:[...root.querySelectorAll('.service')],section:root.querySelector('section')};}
const visible=(cards,ratio=1)=>intersections.at(-1).fn(cards.map(target=>({target,isIntersecting:ratio>0,intersectionRatio:ratio})));
test('card attention begins only after the original entrance and meaningful individual visibility',async()=>{
 const f=attentionFixture();f.section.dataset.motionProgress='.500';const stop=mountCardAttention(f.root,{random:()=>.5});visible(f.cards,.4);vi.advanceTimersByTime(10000);expect(animations).toHaveLength(0);
 visible(f.cards);f.section.dataset.motionProgress='1.000';await Promise.resolve();vi.advanceTimersByTime(5499);expect(animations).toHaveLength(0);vi.advanceTimersByTime(1);expect(animations).toHaveLength(1);expect(Element.prototype.animate.mock.calls[0][1].duration).toBe(1400);
 const sequence=[];for(let i=0;i<5;i++){const a=animations.at(-1);sequence.push(a.element.parentElement.dataset.card);a.complete();await Promise.resolve();vi.advanceTimersByTime(5500);}expect(new Set(sequence.slice(0,4)).size).toBe(4);sequence.slice(1).forEach((id,i)=>expect(id).not.toBe(sequence[i]));stop();
});
test('focus takes priority over hover and suspends one automatic phase without two simultaneous lights',async()=>{
 const f=attentionFixture(),stop=mountCardAttention(f.root,{random:()=>.5});visible(f.cards);vi.advanceTimersByTime(5500);const a=animations[0];a.currentTime=700;
 f.cards[1].dispatchEvent(new Event('pointerover',{bubbles:true}));expect(a.cancel).toHaveBeenCalledOnce();expect(f.cards[1].firstChild.style.opacity).toBe('1');expect(f.cards.filter(c=>c.firstChild.style.opacity==='1')).toHaveLength(1);
 f.cards[2].querySelector('a').dispatchEvent(new FocusEvent('focusin',{bubbles:true}));expect(f.cards[2].firstChild.style.opacity).toBe('1');expect(f.cards[1].firstChild.style.opacity).toBe('0');
 f.cards[2].dispatchEvent(new FocusEvent('focusout',{bubbles:true,relatedTarget:document.body}));f.cards[1].dispatchEvent(new Event('pointerout',{bubbles:true}));expect(animations.at(-1).currentTime).toBe(700);
 a.complete();await Promise.resolve();expect(animations).toHaveLength(2);stop();
});
test('hidden tabs preserve remaining wait, offscreen events reset and reduced motion cancels automatic attention',async()=>{
 const f=attentionFixture(),stop=mountCardAttention(f.root,{random:()=>.5});visible(f.cards);clock=2000;vi.advanceTimersByTime(2000);document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));vi.advanceTimersByTime(20000);expect(animations).toHaveLength(0);
 document.hidden=false;document.dispatchEvent(new Event('visibilitychange'));vi.advanceTimersByTime(3499);expect(animations).toHaveLength(0);vi.advanceTimersByTime(1);expect(animations).toHaveLength(1);
 const card=animations[0].element.parentElement;visible([card],0);vi.advanceTimersByTime(5500);expect(animations).toHaveLength(2);media.matches=true;media.dispatchEvent(new Event('change'));expect(animations[1].cancel).toHaveBeenCalled();vi.advanceTimersByTime(20000);expect(animations).toHaveLength(2);
 stop();await Promise.resolve();visible(f.cards);expect(vi.getTimerCount()).toBe(0);
});
test('one visible last card waits for visibility changes, and missing animation APIs retain static manual feedback',async()=>{
 const f=attentionFixture(),stop=mountCardAttention(f.root,{random:()=>.5});visible([f.cards[0]]);vi.advanceTimersByTime(5500);animations[0].complete();await Promise.resolve();expect(vi.getTimerCount()).toBe(0);visible(f.cards);vi.advanceTimersByTime(5500);expect(animations).toHaveLength(2);stop();
 delete Element.prototype.animate;const g=attentionFixture(),fallback=mountHomeEnhancements(g.root);g.cards[1].dispatchEvent(new Event('pointerover',{bubbles:true}));expect(g.cards[1].firstChild.style.opacity).toBe('1');fallback();
});
test('failed decorative animation cannot block static actions; touch does not act as hover',()=>{
 const f=attentionFixture();Element.prototype.animate=()=>{throw Error('unsupported');};const stop=mountCardAttention(f.root,{random:()=>.5});visible(f.cards);vi.advanceTimersByTime(5500);const event=new Event('pointerover',{bubbles:true});event.pointerType='touch';f.cards[0].dispatchEvent(event);expect(f.cards[0].firstChild.style.opacity).toBe('0');const out=new Event('pointerout',{bubbles:true});out.pointerType='touch';f.cards[0].dispatchEvent(out);stop();
});

test('card attention continues cycling when only two of the four cards stay visible',async()=>{
 const f=attentionFixture(),stop=mountCardAttention(f.root,{random:()=>.5});visible(f.cards.slice(0,2));
 const sequence=[];for(let i=0;i<6;i++){vi.advanceTimersByTime(5500);const a=animations.at(-1);sequence.push(a.element.parentElement.dataset.card);a.complete();await Promise.resolve();}
 expect(animations).toHaveLength(6);expect(new Set(sequence)).toEqual(new Set(['0','1']));sequence.slice(1).forEach((id,i)=>expect(id).not.toBe(sequence[i]));stop();
});
test('FAQ fallback closes only open siblings of this group and ignores close events',()=>{
 const root=el('<details name="sarsa-home-faq" open></details><details name="sarsa-home-faq"></details><details name="another" open></details>');const [a,b,c]=root.children;b.open=true;exclusiveFaq({currentTarget:b});expect(a.open).toBe(false);expect(c.open).toBe(true);b.open=false;exclusiveFaq({currentTarget:b});expect(c.open).toBe(true);
});

test('margin art measures actual empty gutters, pauses offscreen/hidden and disappears when there is no room',async()=>{
 const root=el('<section><div></div></section><div class="overlay"></div>'),target=root.querySelector('section'),canvas=target.firstChild,overlay=root.lastChild;
 root.getBoundingClientRect=()=>rect(0,0,2560,2000);target.getBoundingClientRect=()=>rect(0,250,2560,800);canvas.getBoundingClientRect=()=>rect(680,250,1200,600);
 const stop=mountMarginArt(overlay,target,canvas);expect(overlay.hidden).toBe(false);expect(overlay.style.top).toBe('550px');expect(overlay.style.getPropertyValue('--margin-art-size')).toBe('128px');
 intersections.at(-1).fn([{isIntersecting:true}]);expect(overlay.dataset.running).toBe('true');document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));expect(overlay.dataset.running).toBe('false');
 window.innerWidth=390;window.dispatchEvent(new Event('resize'));expect(overlay.hidden).toBe(true);window.innerWidth=1440;canvas.getBoundingClientRect=()=>rect(100,0,2360,600);resizes.at(-1).fn();expect(overlay.hidden).toBe(true);stop();await Promise.resolve();
 const absent=mountMarginArt(overlay,null,null);expect(overlay.hidden).toBe(true);absent();vi.stubGlobal('ResizeObserver',undefined);vi.stubGlobal('IntersectionObserver',undefined);const fallback=mountMarginArt(overlay,target,target);fallback();
});

test('one back-to-top control moves between a reserved footer slot and a collision-free floating position',async()=>{
 const root=el('<main id="page-content" tabindex="-1"><p>Content</p></main><footer><div><button style="right:24px;bottom:24px">Top</button></div></footer>');
 const main=root.querySelector('main'),slot=root.querySelector('footer>div'),button=slot.firstChild,p=main.firstChild;slot.getBoundingClientRect=()=>rect(0,3000,52,52);let obstacle=rect(0,0,400,200);p.getBoundingClientRect=()=>obstacle;p.getClientRects=()=>[obstacle];
 const stop=mountBackToTop(slot,button);expect(button.dataset.placement).toBe('inline');intersections.at(-1).fn([{isIntersecting:false}]);tick(10);expect(button.hidden).toBe(true);
 window.scrollY=1100;window.dispatchEvent(new Event('scroll'));tick(20);expect(button.hidden).toBe(false);expect(button.dataset.placement).toBe('floating');button.focus();obstacle=rect(1350,810,80,80);p.dispatchEvent(new Event('toggle',{bubbles:true}));tick(30);expect(button.hidden).toBe(true);expect(document.activeElement).toBe(main);
 intersections.at(-1).fn([{isIntersecting:true}]);tick(40);expect(button.hidden).toBe(false);expect(button.parentElement).toBe(slot);main.append(document.createElement('a'));await Promise.resolve();tick(50);stop();window.dispatchEvent(new Event('resize'));expect(frames.size).toBe(0);
 vi.stubGlobal('IntersectionObserver',undefined);vi.stubGlobal('requestAnimationFrame',undefined);const fallback=mountBackToTop(slot,button);window.dispatchEvent(new Event('scroll'));fallback();
});

test('Top tolerates missing observation, absent offsets, detached content and queued callbacks after teardown',()=>{
 const root=el('<main id="page-content" tabindex="-1"><p>Content</p></main><footer><div><button>Top</button></div></footer>'),slot=root.querySelector('footer>div'),button=slot.firstChild,p=root.querySelector('p');
 slot.getBoundingClientRect=()=>rect(0,3000,52,52);p.getClientRects=()=>[];
 vi.stubGlobal('MutationObserver',undefined);const stop=mountBackToTop(slot,button);window.scrollY=1200;intersections.at(-1).fn([{isIntersecting:false}]);window.dispatchEvent(new Event('resize'));tick(10);expect(button.hidden).toBe(false);
 p.remove();window.dispatchEvent(new Event('scroll'));window.dispatchEvent(new Event('scroll'));tick(20);expect(button.hidden).toBe(false);
 window.dispatchEvent(new Event('resize'));const stale=[...frames.values()][0];stop();expect(frames.size).toBe(0);stale(30);intersections.at(-1).fn([{isIntersecting:true}]);expect(frames.size).toBe(0);
});

test('unsupported visibility observers leave manual card feedback working without timers',()=>{
 vi.stubGlobal('IntersectionObserver',class{constructor(){throw Error('unsupported');}});const f=attentionFixture(),stop=mountCardAttention(f.root);f.cards[0].dispatchEvent(new Event('pointerover',{bubbles:true}));expect(f.cards[0].firstChild.style.opacity).toBe('1');expect(vi.getTimerCount()).toBe(0);stop();
});

test('failed optional observers leave margin art static and Top in its footer slot',()=>{
 const root=el('<main id="page-content" tabindex="-1"></main><section><div></div></section><div class="overlay"></div><footer><div><button>Top</button></div></footer>');
 for(const api of ['ResizeObserver','IntersectionObserver','MutationObserver'])vi.stubGlobal(api,class{constructor(){throw Error('unsupported');}});
 const section=root.querySelector('section'),overlay=root.querySelector('.overlay');
 const stopArt=mountMarginArt(overlay,section,section.firstChild);
 const slot=root.querySelector('footer>div'),button=slot.firstChild,stopTop=mountBackToTop(slot,button);
 expect(button.dataset.placement).toBe('inline');expect(button.hidden).toBe(false);expect(overlay.dataset.running).not.toBe('true');
 stopArt();stopTop();expect(frames.size).toBe(0);
});

test('About background bounds subtract only the service-list growth and follow resizing and cleanup',async()=>{
 const root=el('<div class="consultation-grid"><div><p>Intro</p></div><div class="service-list"><div class="service-row"><div class="row-actions" style="margin-top:12px"></div></div></div></div>');
 const intro=root.querySelector('.consultation-grid>div'),list=root.querySelector('.service-list'),row=root.querySelector('.service-row'),actions=root.querySelector('.row-actions');
 intro.getBoundingClientRect=()=>rect(0,100,300,300);let natural=60;intro.firstChild.getBoundingClientRect=()=>rect(0,100,300,natural);
 let listHeight=156;list.getBoundingClientRect=()=>rect(0,100,300,listHeight);row.getBoundingClientRect=()=>rect(0,100,300,listHeight);actions.getBoundingClientRect=()=>rect(0,200,100,44);
 const stop=mountAboutLayout(root);expect(root.style.getPropertyValue('--about-row-growth')).toBe('56px');expect(root.style.getPropertyValue('--about-row-growth-60')).toBe('33.6px');resizes.at(-1).fn();
 natural=140;window.dispatchEvent(new Event('resize'));expect(root.style.getPropertyValue('--about-row-growth')).toBe('16px');
 actions.style.position='absolute';window.dispatchEvent(new Event('resize'));expect(root.style.getPropertyValue('--about-row-growth')).toBe('0px');
 stop();resizes.at(-1).fn();await Promise.resolve();expect(root.style.getPropertyValue('--about-row-growth')).toBe('');
 vi.stubGlobal('ResizeObserver',undefined);const absent=mountAboutLayout(root);absent();
 vi.stubGlobal('ResizeObserver',class{constructor(){throw Error('unsupported');}});actions.style.marginTop='';const failed=mountAboutLayout(root);failed();
});
