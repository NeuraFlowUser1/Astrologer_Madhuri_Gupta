/** PRIVATE DEV-ONLY HARNESS. This HTML is not a Vite build entry or public asset.
 * Approved records exercise the real page/frame in StrictMode with test navigation.
 * Browser checks intercept the local display-state read; no provider operation occurs.
 */
import React,{StrictMode,useLayoutEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,Routes,Route,useLocation,useNavigate,useNavigationType} from 'react-router-dom';
import Testimonials from '../../src/pages/Testimonials.jsx';
import {SiteHeader,SiteFooter} from '../../src/site/SiteFrame.jsx';
import {observeHeader,createPublicScroller} from '../../src/site/public-scroll.mjs';
import {productState} from '../../src/site/product-state.mjs';
import {testimonialStories} from '../fixtures/testimonial-stories.mjs';
import '../../src/index.css';
function PrivatePreview(){
  const shell=useRef(null),header=useRef(null),main=useRef(null),scroller=useRef(null);
  const location=useLocation(),navigate=useNavigate(),type=useNavigationType();
  useLayoutEffect(()=>{
    const stop=observeHeader(shell.current,header.current);
    scroller.current=createPublicScroller({main:main.current,header:header.current,navigate});
    return()=>{stop();scroller.current.dispose();scroller.current=null;};
  },[navigate]);
  useLayoutEffect(()=>{scroller.current?.route(location,type);},[location,type]);
  return <div className="sarsa-site" ref={shell}><SiteHeader headerRef={header}/><a className="sarsa-skip" href="#page-content">Skip to content</a><main id="page-content" ref={main} tabIndex={-1}><Routes><Route path="/testimonials" element={<Testimonials stories={testimonialStories}/>}/><Route path="*" element={<section><h1>Private navigation check</h1></section>}/></Routes></main><SiteFooter showBackToTop scrollerRef={scroller}/></div>;
}
await productState.refresh({force:true});
window.history.replaceState({},'','/testimonials');
createRoot(document.getElementById('root')).render(<StrictMode><BrowserRouter><PrivatePreview/></BrowserRouter></StrictMode>);
