import {useLayoutEffect,useRef} from 'react';

/** React keeps ownership of both modal and inline readers, including their cleanup. */
export default function TestimonialReader({story,opener,native,onClose}){
  const dialog=useRef(null),title=useRef(null),restoreFocus=useRef(false);
  const close=()=>{restoreFocus.current=true;onClose();};
  useLayoutEffect(()=>{
    const element=dialog.current,oldOverflow=document.body.style.overflow;
    if(native){element.showModal();document.body.style.overflow='hidden';}
    element.scrollTop=0;title.current.focus({preventScroll:native});
    return()=>{
      if(native){element.close();document.body.style.overflow=oldOverflow;}
      // Leaving the route must not focus an element that is about to be removed.
      if(restoreFocus.current){
        const target=opener?.isConnected?opener:element.closest('.sarsa-testimonials')?.querySelector('#stories-title');
        target?.focus({preventScroll:true});
      }
    };
  },[native,opener]);
  const keyDown=event=>{
    if(event.key==='Escape'){event.preventDefault();close();}
    if(native&&event.key==='Tab'){
      const controls=[...dialog.current.querySelectorAll('button:not(:disabled),a[href],[tabindex="0"]')];
      const first=controls[0],last=controls.at(-1),current=document.activeElement;
      if(!controls.includes(current)||(!event.shiftKey&&current===last)||(event.shiftKey&&current===first)){
        event.preventDefault();(event.shiftKey?last:first)?.focus();
      }
    }
  };
  return <dialog ref={dialog} id="story-dialog" aria-labelledby="dialog-title" open={native?undefined:true}
    data-inline={native?undefined:'true'} role={native?undefined:'region'} onKeyDown={keyDown}
    onCancel={event=>{event.preventDefault();close();}}>
    <div className="dialog-top"><p className="eyebrow">{story.service}</p><button type="button" className="dialog-close" id="dialog-close" aria-label="Close story" onClick={close}><span>Close</span><span aria-hidden="true">×</span></button></div>
    <div className="dialog-body"><h2 ref={title} id="dialog-title" tabIndex={-1}>{story.name}&apos;s story</h2><p className="dialog-city">{story.city}</p><blockquote id="dialog-quote" lang={story.lang}>{story.quote}</blockquote><h3>The question I brought</h3><p lang={story.lang}>{story.context}</p><div id="dialog-paragraphs" lang={story.lang}>{story.paragraphs.map((text,index)=><p key={index}>{text}</p>)}</div></div>
    <div className="dialog-bottom"><svg aria-hidden="true"><use href="#testimonial-icon-star"/></svg><span>Shared after a consultation with Madhuri.</span></div>
  </dialog>;
}
