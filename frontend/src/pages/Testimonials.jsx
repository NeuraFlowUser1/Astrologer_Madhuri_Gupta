import {Fragment,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {BookingLink as Link} from '../site/BookingProduct.jsx';
import TestimonialReader from '../site/TestimonialReader.jsx';
import {clientTestimonials} from '../site/testimonials-content.mjs';
import {buildTestimonialIndex,openingExcerpt,testimonialServices} from '../site/testimonials-model.mjs';
import {mountTestimonialsMotion} from '../site/testimonials-motion.mjs';
import featureImage from '../site/media/services/kundli-prediction-primary-800.webp';
import '../site/testimonials.css';

function Icon({name,className=''}){return <svg className={className} aria-hidden="true"><use href={'#testimonial-icon-'+name}/></svg>;}
function Symbols(){return <svg className="symbol-library" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs>
  <symbol id="testimonial-icon-arrow" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6"/></symbol>
  <symbol id="testimonial-icon-star" viewBox="0 0 32 32"><path d="m16 2 3.8 10.2L30 16l-10.2 3.8L16 30l-3.8-10.2L2 16l10.2-3.8Z"/></symbol>
  <symbol id="testimonial-icon-chart" viewBox="0 0 40 40"><rect x="5" y="5" width="30" height="30" rx="2"/><path d="m20 5 15 15-15 15L5 20Zm-15 0 30 30m0-30L5 35"/></symbol>
  <symbol id="testimonial-icon-matching" viewBox="0 0 40 40"><circle cx="15" cy="20" r="11"/><circle cx="25" cy="20" r="11"/><path d="M20 9v22"/></symbol>
  <symbol id="testimonial-icon-vastu" viewBox="0 0 40 40"><path d="m4 19 16-14 16 14M8 16v19h24V16M17 35V24h6v11"/><circle cx="20" cy="15" r="3"/></symbol>
  <symbol id="testimonial-icon-number" viewBox="0 0 40 40"><circle cx="20" cy="20" r="15"/><path d="M15 13h10L17 28m-2-6h10"/></symbol>
</defs></svg>;}
function Person({story,light=false}){return <div className="person"><span className={'initials'+(light?' light':'')}>{story.initials}</span><p><strong>{story.name}</strong><span>{story.city}</span></p></div>;}
function ReadAction({story,onRead,children='Read the full story',light=false,measure=false,className=''}){
  const contents=<>{children} <Icon name="arrow"/></>;
  return measure?<span className={'text-action'+(light?' light-action':'')}>{contents}</span>:<button type="button" className={'text-action '+className+(light?' light-action':'')} aria-label={children+' from '+story.name} data-story-id={story.id} onClick={event=>onRead(story,event.currentTarget)}>{contents}</button>;
}
function FeatureContents({story,onRead,measure=false}){return <>
  <span className="service-label">{story.service}</span><blockquote className="featured-quote" lang={story.lang}>{story.quote}</blockquote>
  <p className="featured-context" lang={story.lang}>{story.context}</p><Person story={story} light/>
  <ReadAction story={story} onRead={onRead} light measure={measure}/>
</>;}
function ThemeContents({story,onRead,measure=false}){return <>
  <span className="echo-mark" aria-hidden="true">“</span><blockquote className="echo-quote" lang={story.lang}>{story.quote}</blockquote>
  <p className="echo-attribution"><strong>{story.name}</strong><span>{story.service}</span></p>
  <ReadAction story={story} onRead={onRead} measure={measure}>Read this story</ReadAction>
</>;}
function OpeningArtwork({stories}){
  const main=stories.find(story=>story.category==='kundli-prediction')||stories[0];
  const back=stories.find(story=>story.category==='kundli-matching');
  const front=stories.find(story=>story.category==='vastu-consultation');
  return <div className="paper-constellation" data-ambient>
    <svg className="constellation" viewBox="0 0 500 480" aria-hidden="true"><ellipse className="orbit-draw" cx="256" cy="235" rx="201" ry="177" transform="rotate(-24 256 235)"/><path className="thread-draw" d="M65 331Q31 147 167 73T435 157Q483 291 348 408"/><g className="orbital-dot"><circle cx="82" cy="106" r="4"/><circle cx="428" cy="350" r="3"/></g><path className="opening-star" d="m427 49 4.5 13.5L445 67l-13.5 4.5L427 85l-4.5-13.5L409 67l13.5-4.5Z"/><path className="opening-star small-star" d="m58 399 3 9 9 3-9 3-3 9-3-9-9-3 9-3Z"/></svg>
    {back&&<div className="paper-note note-back" data-paper="back"><Icon className="small-motif" name="matching"/><p lang={back.lang}>“{openingExcerpt(back)}”</p><span>{back.name} · {back.city}</span></div>}
    <div className="paper-note note-main" data-paper="main"><span className="quote-glyph" aria-hidden="true">“</span><blockquote lang={main.lang}>{openingExcerpt(main)}</blockquote><div className="note-person"><span className="initials light">{main.initials}</span><p>{main.name}<span>{main.city} · {main.service}</span></p></div><Icon className="note-chart" name="chart"/></div>
    {front&&<div className="paper-note note-front" data-paper="front"><Icon className="small-motif" name="vastu"/><p lang={front.lang}>“{openingExcerpt(front)}”</p><span>{front.name} · {front.city}</span></div>}
  </div>;
}

function WaitingArtwork(){return <div className="paper-constellation reviews-waiting-art" data-ambient aria-hidden="true">
  <svg className="constellation" viewBox="0 0 500 480"><ellipse cx="250" cy="235" rx="204" ry="178" transform="rotate(-24 250 235)"/><path className="thread-draw" d="M65 331Q31 147 167 73T435 157Q483 291 348 408"/><path className="opening-star" d="m427 49 4.5 13.5L445 67l-13.5 4.5L427 85l-4.5-13.5L409 67l13.5-4.5Z"/></svg>
  <div className="reviews-waiting-photo" data-paper="main"><img src={featureImage} alt="" width="800" height="533" decoding="async"/><span className="reviews-waiting-seal"><Icon name="chart"/></span></div>
</div>;}

/** Content is passed only by the private test harness; the public route uses real client data. */
export default function Testimonials({stories=clientTestimonials}){
  const index=useMemo(()=>buildTestimonialIndex(stories),[stories]);
  const [filter,setFilter]=useState('all'),[visibleLimit,setVisibleLimit]=useState(6),[featureIndex,setFeatureIndex]=useState(0),[activeTheme,setActiveTheme]=useState('heard'),[reading,setReading]=useState(null);
  const root=useRef(null),motion=useRef(null),focusNew=useRef(null),previous=useRef({filter:'all',visibleLimit:6,featureIndex:0,activeTheme:'heard'});
  const matches=index.stories.filter(story=>filter==='all'||story.category===filter),shown=matches.slice(0,visibleLimit);
  const featurePosition=index.featured.length?featureIndex%index.featured.length:0;
  const featured=index.featured[featurePosition];
  const theme=index.themes.find(item=>item.id===activeTheme)||index.themes[0];
  const readStory=reading&&index.byId.get(reading.id);
  useLayoutEffect(()=>{
    motion.current=mountTestimonialsMotion(root.current);
    return()=>{motion.current.dispose();motion.current=null;};
  },[]);
  useLayoutEffect(()=>{
    const old=previous.current;
    if(old.filter!==filter||old.visibleLimit!==visibleLimit)motion.current.updateGrid();
    if(old.featureIndex!==featureIndex)motion.current.updateFeature();
    if(old.activeTheme!==activeTheme)motion.current.updateTheme();
    previous.current={filter,visibleLimit,featureIndex,activeTheme};
    if(focusNew.current!==null){root.current.querySelectorAll('.story-card')[focusNew.current]?.focus({preventScroll:true});focusNew.current=null;}
  },[filter,visibleLimit,featureIndex,activeTheme]);
  useLayoutEffect(()=>{motion.current.setReaderOpen(Boolean(readStory));},[readStory]);
  function openStory(story,opener,origin){setReading({id:story.id,opener,origin,native:typeof HTMLDialogElement!=='undefined'&&typeof HTMLDialogElement.prototype.showModal==='function'});}
  function reader(origin){return readStory&&reading.origin===origin?<TestimonialReader key={readStory.id} story={readStory} opener={reading.opener} native={reading.native} onClose={()=>setReading(null)}/>:null;}
  function selectFilter(next){setReading(null);setFilter(next);setVisibleLimit(6);}
  function moveFeature(direction){setReading(null);setFeatureIndex(value=>(value+direction+index.featured.length)%index.featured.length);}
  return <div className="sarsa-testimonials" ref={root}><Symbols/>
    <section className="opening chapter" aria-labelledby="opening-title" data-scene="opening">
      <div className="container opening-grid"><div className="opening-copy">
        <p className="eyebrow"><span className="short-rule" aria-hidden="true"/> Customer reviews</p><h1 id="opening-title">{index.stories.length>0?<>What people say<br/>about Madhuri.</>:<>Reviews from<br/>Madhuri&apos;s clients.</>}</h1>
        {index.stories.length>0?<><p className="opening-intro">People come to Madhuri ji with questions about work, marriage, their home and more.</p><p className="opening-intro second">Here, they share what their consultation was like, in their own words.</p><Link className="button primary read-stories" to="/testimonials#stories" data-public-scroll>Read client reviews <Icon name="arrow"/></Link><p className="handwritten" lang="hi-Latn">Madhuri ji se baat karke unhe kaisa laga?</p></>:<><p className="opening-intro" role="status">Reviews will be added here.</p><p className="opening-intro second">This page will share feedback from people who have had a consultation with Madhuri ji.</p><p className="reviews-share-copy">Have you spoken with Madhuri ji? You can share your experience with us.</p><div className="reviews-waiting-actions"><Link className="button primary" to="/contact">Share your experience <Icon name="arrow"/></Link><Link className="button secondary" to="/services">Explore the services</Link></div></>}
      </div>{index.stories.length>0?<OpeningArtwork stories={index.stories}/>:<WaitingArtwork/>}</div>
      <div className="chapter-end container" aria-hidden="true"><span/><Icon name="star"/><span/></div>
    </section>

    {featured&&<section className="featured chapter" aria-labelledby="featured-heading" data-scene="featured"><div className="container">
      <div className="section-intro feature-intro"><div><p className="eyebrow">Their time with Madhuri</p><h2 id="featured-heading">How their<br/>consultation went.</h2></div><p>Read what they asked Madhuri ji and how they felt after speaking with her.</p></div>
      <div className="feature-grid"><div className="feature-photo" data-enter="photo"><img src={featureImage} alt="" width="800" height="533" loading="lazy" decoding="async"/><div className="photo-note"><span className="tiny-star" aria-hidden="true">✧</span><span>Let&apos;s talk about<br/>your questions.</span></div></div>
        <div className="feature-reader"><div className="feature-stack"><div id="featured-story" data-enter="quote"><FeatureContents story={featured} onRead={(story,opener)=>openStory(story,opener,'feature')}/></div>{index.featured.map(story=><div className="feature-measure" aria-hidden="true" inert key={story.id}><FeatureContents story={story} measure/></div>)}</div>
          {index.featured.length>1&&<div className="feature-controls"><span className="position"><span id="feature-index">{String(featurePosition+1).padStart(2,'0')}</span><span className="position-rule" aria-hidden="true"/><span>{String(index.featured.length).padStart(2,'0')}</span></span><div className="arrow-controls"><button className="round-control" id="feature-prev" type="button" aria-label="Previous featured story" onClick={()=>moveFeature(-1)}><Icon className="reverse" name="arrow"/></button><button className="round-control" id="feature-next" type="button" aria-label="Next featured story" onClick={()=>moveFeature(1)}><Icon name="arrow"/></button></div></div>}
          <p className="sr-only" aria-live="polite" aria-atomic="true">{featured.name}, featured story {featurePosition+1} of {index.featured.length}</p>{!reading?.native&&reader('feature')}
        </div>
      </div>
    </div></section>}

    {index.stories.length>0&&<section className="collection chapter" id="stories" aria-labelledby="stories-title" data-scene="collection">
      <span className="sarsa-scroll-destination" data-scroll-destination="stories" tabIndex={-1}>Client reviews</span>
      <div className="container"><div className="section-intro collection-intro"><div><p className="eyebrow">Reviews by service</p><h2 id="stories-title" tabIndex={-1}>Read what our<br/>clients have shared.</h2></div><p>Read their feedback on Kundli, Vastu and Numerology consultations.</p></div>
        <div className="filter-bar"><div className="filters" role="group" aria-label="Filter stories by service">{[{id:'all',label:'All stories'},...testimonialServices].map(service=><button key={service.id} type="button" data-filter={service.id} aria-pressed={filter===service.id} onClick={()=>selectFilter(service.id)}>{service.label}</button>)}</div><p id="result-count" className="result-count" role="status" aria-live="polite" aria-atomic="true">Showing {shown.length} of {matches.length} {matches.length===1?'story':'stories'}</p></div>
        <div className="story-grid" id="story-grid">{shown.map(story=><Fragment key={story.id}><article className="story-card" data-story={story.id} tabIndex={-1}><p className="card-heading"><Icon name={testimonialServices.find(service=>service.id===story.category).icon}/><span>{story.service}</span></p><blockquote lang={story.lang}>{story.quote}</blockquote><div className="card-bottom"><div className="card-person"><span className="initials">{story.initials}</span><p><strong>{story.name}</strong><span>{story.city}</span></p></div><ReadAction className="card-read" story={story} onRead={(item,opener)=>openStory(item,opener,'collection')}>Read full story</ReadAction></div></article>{!reading?.native&&reading?.id===story.id&&reader('collection')}</Fragment>)}</div>
        {matches.length===0&&<div id="empty-stories" className="empty-stories"><p>There are no stories in this group yet.</p><button type="button" className="button secondary" id="reset-filter" onClick={()=>{selectFilter('all');root.current.querySelector('[data-filter=all]').focus();}}>Show all stories</button></div>}
        <div className="more-row">{shown.length<matches.length&&<button type="button" className="button secondary" id="more-stories" onClick={()=>{focusNew.current=shown.length;setReading(null);setVisibleLimit(value=>value+6);}}>See more stories <Icon name="arrow"/></button>}<p id="collection-note">{filter==='all'?'Choose a service above to read reviews about it.':'These reviews are from people who booked this service.'}</p></div>
      </div>
    </section>}

    {theme&&<section className="echoes chapter" aria-labelledby="echoes-title" data-scene="echoes"><div className="container echoes-grid">
      <div className="echoes-intro"><p className="eyebrow">What they appreciated</p><h2 id="echoes-title">What they liked<br/>about Madhuri.</h2><div className="theme-selectors" role="group" aria-label="Choose a conversation theme">{index.themes.map(item=><button type="button" key={item.id} data-theme={item.id} aria-pressed={theme.id===item.id} onClick={()=>{setReading(null);setActiveTheme(item.id);}}>{item.label} <Icon name="arrow"/></button>)}</div></div>
      <div className="echo-reading" data-enter="echo"><svg className="echo-line" viewBox="0 0 470 65" preserveAspectRatio="none" aria-hidden="true"><path d="M0 40Q135-30 230 36T470 20"/><circle cx="230" cy="36" r="4"/></svg><div className="echo-stack"><div className="echo-content"><ThemeContents story={theme.story} onRead={(story,opener)=>openStory(story,opener,'theme')}/></div>{index.themes.map(item=><div key={item.id} className="echo-measure" aria-hidden="true" inert><ThemeContents story={item.story} measure/></div>)}</div><p className="sr-only" aria-live="polite" aria-atomic="true">{theme.story.name}, {theme.story.service}</p>{!reading?.native&&reader('theme')}</div>
    </div></section>}

    {index.stories.length>0&&<section className="invitation chapter" aria-labelledby="invitation-title" data-scene="invitation"><div className="container invitation-grid">
      <div className="invitation-art" aria-hidden="true"><svg viewBox="0 0 320 290"><g className="sun-lines"><circle cx="157" cy="126" r="63"/><circle cx="157" cy="126" r="48"/><path d="M157 32V16m0 220v-16M63 126H47m220 0h-16M91 60 80 49m154 154-11-11M91 192l-11 11M234 49l-11 11M121 39l-6-15m84 204-6-15M70 90l-15-6m204 84-15-6M70 162l-15 6m204-84-15 6M121 213l-6 15m84-204-6 15"/></g><path className="invitation-path" d="M7 269Q112 259 157 198T304 229"/><path d="m157 104 5 16 16 6-16 6-5 16-5-16-16-6 16-6Z"/></svg></div>
      <div className="invitation-copy"><p className="eyebrow">Talk to Madhuri</p><h2 id="invitation-title">Would you like<br/>to speak to Madhuri?</h2><p>Read about the services, or book a consultation to talk through your questions.</p><div className="invitation-actions"><Link className="button secondary" to="/services">Explore the services</Link><Link className="button primary" to="/booking" bookingMode="hide">Book an appointment <span aria-hidden="true">↗</span></Link></div></div>
    </div></section>}
    {reading?.native&&reader(reading.origin)}
  </div>;
}
