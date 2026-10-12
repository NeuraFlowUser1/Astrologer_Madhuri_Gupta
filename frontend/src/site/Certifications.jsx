import {useLayoutEffect,useRef,useState} from 'react';
import {Button,Dialog,Heading,Modal,ModalOverlay} from 'react-aria-components';
import {certificates} from './certificates-content.mjs';
import {mountCertificationsMotion} from './certifications-motion.mjs';
import './certifications.css';

/** One image request per open document; changing it resets fit/error state. */
export function CertificateImage({certificate,zoomed}){
  const [failed,setFailed]=useState(false),[loaded,setLoaded]=useState(false);
  return failed?<p className="certificate-image-error" role="status">This image could not load. You can still <a href={certificate.original} target="_blank" rel="noopener noreferrer">open the original certificate</a>.</p>:
    <div className="certificate-image-canvas" data-zoomed={zoomed}>
      {!loaded&&<span className="certificate-loading" role="status">Loading certificate…</span>}
      <img src={certificate.full} width={certificate.width} height={certificate.height}
        alt={certificate.title+' certificate issued by '+certificate.issuer}
        onError={()=>setFailed(true)} onLoad={()=>setLoaded(true)} decoding="async"/>
    </div>;
}

function CertificateViewer({initialIndex,onClose}){
  const [index,setIndex]=useState(initialIndex),[zoomed,setZoomed]=useState(false);
  const certificate=certificates[index],pane=useRef(null),previousButton=useRef(null),nextButton=useRef(null),pendingFocus=useRef(null);
  useLayoutEffect(()=>{pendingFocus.current?.current?.focus({preventScroll:true});pendingFocus.current=null;},[index]);
  function move(next){
    // Disabling the active boundary button otherwise drops browser focus to body.
    if(next===0)pendingFocus.current=nextButton;
    else if(next===certificates.length-1)pendingFocus.current=previousButton;
    setIndex(next);setZoomed(false);pane.current.scrollTo?.(0,0);
  }
  return <ModalOverlay className="certificate-overlay" isOpen isDismissable onOpenChange={open=>{if(!open)onClose();}}>
    <Modal className="certificate-modal"><Dialog className="certificate-dialog">
      <div className="certificate-reader-top"><div><p className="certificate-reader-position" aria-live="polite" aria-atomic="true">Certificate {index+1} of {certificates.length}</p><Heading slot="title">{certificate.title}</Heading><p>{certificate.issuer}</p></div><Button autoFocus className="certificate-close" onPress={onClose} aria-label="Close certificate">Close <span aria-hidden="true">×</span></Button></div>
      <div className="certificate-image-pane" ref={pane} tabIndex={0} aria-label={zoomed?'Enlarged certificate. Scroll to read all of it.':'Certificate image'}>
        <CertificateImage key={certificate.id} certificate={certificate} zoomed={zoomed}/>
      </div>
      <div className="certificate-reader-controls"><div className="certificate-paging"><Button ref={previousButton} isDisabled={index===0} onPress={()=>move(index-1)} aria-label="Previous certificate">← Previous</Button><Button ref={nextButton} isDisabled={index===certificates.length-1} onPress={()=>move(index+1)} aria-label="Next certificate">Next →</Button></div><Button aria-pressed={zoomed} onPress={()=>setZoomed(value=>!value)}>{zoomed?'Fit to screen':'Zoom in'}</Button><a href={certificate.original} target="_blank" rel="noopener noreferrer">Open original file <span aria-hidden="true">↗</span></a></div>
    </Dialog></Modal>
  </ModalOverlay>;
}

/** Supplied education evidence, separate from existing About animation owners. */
export default function Certifications(){
  const root=useRef(null),[selected,setSelected]=useState(null);
  useLayoutEffect(()=>mountCertificationsMotion(root.current),[]);
  return <section className="sarsa-certifications" id="certifications" ref={root} aria-labelledby="certifications-title">
    <div className="certifications-wrap">
      <div className="certifications-intro"><div className="certifications-rule" aria-hidden="true"/><h2 id="certifications-title">Her studies and certificates</h2><p>Madhuri has studied Jyotish and completed courses in astrology and numerology. Here are the certificates from those courses.</p><p className="certifications-instruction">Select a certificate to see it up close.</p></div>
      <div className="certificates-grid">{certificates.map((certificate,index)=><article className={'certificate-item '+certificate.orientation} key={certificate.id}>
        <button type="button" className="certificate-preview" onClick={()=>setSelected(index)} aria-label={'View '+certificate.title+' certificate'} aria-haspopup="dialog"><img src={certificate.thumbnail} width={certificate.width} height={certificate.height} alt={certificate.title+' certificate'} loading="lazy" decoding="async"/><span className="certificate-view-label">View certificate <span aria-hidden="true">↗</span></span></button>
        <div className="certificate-caption"><p className="certificate-period">{certificate.period}</p><h3>{certificate.title}</h3><p className="certificate-issuer">{certificate.issuer}</p><p className="certificate-explanation">{certificate.explanation}</p></div>
      </article>)}</div>
    </div>
    {selected!==null&&<CertificateViewer initialIndex={selected} onClose={()=>setSelected(null)}/>}
  </section>;
}
