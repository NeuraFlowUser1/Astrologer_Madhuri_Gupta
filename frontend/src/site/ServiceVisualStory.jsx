import {useEffect,useRef,useState} from 'react';
import ServiceMedia,{imageSource} from './ServiceMedia.jsx';
import {visualStories} from './service-visual-content.mjs';
import './service-visual.css';

/** Manual imagery only. Booking and service availability stay with BookingProduct. */
export default function ServiceVisualStory({serviceId,name}){
  const stories=visualStories[serviceId];
  const [topic,setTopic]=useState(0),[displayed,setDisplayed]=useState(0),[requested,setRequested]=useState(0);
  const [previous,setPrevious]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(null),[reload,setReload]=useState(0);
  const token=useRef(0),disposed=useRef(false),fadeTimer=useRef(0),failedImages=useRef(new Set());
  useEffect(()=>{disposed.current=false;return()=>{disposed.current=true;token.current++;clearTimeout(fadeTimer.current);};},[]);
  const image=imageSource(serviceId,displayed,true),story=stories[topic];

  async function requestImage(index,retry=false){
    if(index<0||index>1)return;
    const request=++token.current;
    setRequested(index);setError(null);
    if(index===displayed&&!retry){setBusy(false);if(failedImages.current.has(index))setError(index);return;}
    setBusy(true);
    const source=imageSource(serviceId,index,true),probe=new Image();
    try{
      // Match the rendered responsive request so the decoded asset is reused.
      probe.sizes='(max-width: 700px) calc(100vw - 48px), (max-width: 1240px) 55vw, 640px';
      probe.srcset=source.srcSet;probe.src=source.src;
      await probe.decode();
      if(disposed.current||request!==token.current)return;
      failedImages.current.delete(index);setError(null);
      clearTimeout(fadeTimer.current);
      const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
      setPrevious(index===displayed||reduced?null:displayed);setDisplayed(index);setReload(n=>n+1);setBusy(false);
      if(!reduced)fadeTimer.current=setTimeout(()=>{if(!disposed.current)setPrevious(null);},240);
    }catch{
      if(disposed.current||request!==token.current)return;
      failedImages.current.add(index);setBusy(false);setRequested(displayed);setError(index);
    }
  }
  const failed=index=>{if(!disposed.current){failedImages.current.add(index);setError(index);}};
  return <section className="service-visual-story" data-visual-stage data-service-id={serviceId} aria-label={name+' in pictures'}>
    <div className="visual-story-grid">
      <figure className="story-viewer">
        <div className="story-picture" data-visual-part="photo" aria-busy={busy}>
          {previous!==null&&<ServiceMedia key={'previous-'+previous} serviceId={serviceId} index={previous} detail className="story-outgoing" hidden/>}
          <ServiceMedia key={displayed+'-'+reload} serviceId={serviceId} index={displayed} detail className={previous!==null?'story-incoming':''} onFailure={failed}/>
          <div className="story-accents" aria-hidden="true">
            {serviceId==='kundli-matching'?<svg viewBox="0 0 100 100" preserveAspectRatio="none"><path data-visual-ambient d={`M${image.markers[0].join(' ')} Q50 25 ${image.markers[1].join(' ')}`}/></svg>:
            serviceId==='kundli-prediction'?<i className="chart-edge-light" data-visual-ambient/>:
            serviceId==='vastu-consultation'?<i className="space-sunlight" data-visual-ambient/>:
            image.markers.map(([x,y],i)=><i key={i} className="number-slip-light" data-visual-ambient style={{left:x+'%',top:y+'%'}}/>)}
          </div>
          <div className="story-markers" data-visual-part="markers" aria-hidden="true">{image.markers.map(([x,y],i)=><span key={i} className="story-marker" data-active={topic===i} style={{left:x+'%',top:y+'%'}}>{i+1}</span>)}</div>
          <span className="illustration-label">Illustration</span>
        </div>
        <div className="story-controls" data-visual-part="controls" aria-label="Service pictures">
          <button type="button" aria-disabled={requested===0} onClick={()=>{if(requested>0)void requestImage(requested-1);}}>← Previous</button>
          <span>{displayed+1} of 2</span>
          <button type="button" aria-disabled={requested===1} onClick={()=>{if(requested<1)void requestImage(requested+1);}}>Next →</button>
        </div>
        <figcaption className="story-image-caption">{image.caption}</figcaption>
        <div className="story-image-status" role="status" aria-live="polite">
          {busy?'Loading the next picture…':error!==null?<><span>This picture could not load.</span> <button type="button" onClick={()=>void requestImage(error,true)}>Retry picture {error+1}</button></>:''}
        </div>
      </figure>
      <div className="story-copy" data-visual-part="copy">
        <p className="eyebrow">{name.toUpperCase()} · TAKE A CLOSER LOOK</p>
        <div className="story-heading-stack"><h2>{story[1]}</h2>{stories.map(s=><h2 key={s[0]} className="story-measure" aria-hidden="true">{s[1]}</h2>)}</div>
        <div className="story-caption-stack" aria-live="polite" aria-atomic="true"><p>{story[2]}</p>{stories.map(s=><p key={s[0]} className="story-measure" aria-hidden="true">{s[2]}</p>)}</div>
        <div className="story-choices" aria-label="Explore the ideas">{stories.map((s,i)=><button key={s[0]} type="button" aria-pressed={topic===i} onClick={()=>setTopic(i)}>{i+1}. {s[0]}</button>)}</div>
      </div>
    </div>
  </section>;
}
