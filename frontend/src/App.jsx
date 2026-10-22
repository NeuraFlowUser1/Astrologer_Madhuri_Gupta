import React, { useEffect, useLayoutEffect, useRef, lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, useLocation, useNavigate, useNavigationType } from 'react-router-dom'
import {writePageMetadata} from './site/page-metadata.mjs'
import {useBookingProduct,ProductNavigationCheck,UnavailablePage,BookingRoute} from './site/BookingProduct.jsx'
const BookingReceipt = lazy(() => import('./pages/BookingReceipt.jsx'))
const BookingAccess = lazy(() => import('./pages/BookingAccess.jsx'))
import {SiteHeader,SiteFooter} from './site/SiteFrame.jsx'
import {observeHeader,createPublicScroller} from './site/public-scroll.mjs'
import KundliPrediction from './pages/KundliPrediction.jsx'
import PrashnaKundali from './pages/PrashnaKundali.jsx'
import ServiceDetail from './pages/ServiceDetail.jsx'
import PolicyPage from './pages/PolicyPage.jsx'
import Home from './pages/Home.jsx'
import About from './pages/About.jsx'
import Services from './pages/Services.jsx'
const Booking = lazy(() => import('./pages/Booking.jsx'))
import ContactPage from './pages/ContactPage.jsx'
import Testimonials from './pages/Testimonials.jsx'

export function AppShell() {
  const location = useLocation()
  const navigate=useNavigate(),navigationType=useNavigationType();
  const navigation=useRef(navigate);navigation.current=navigate;
  const shell=useRef(null),header=useRef(null),main=useRef(null),scroller=useRef(null);
  useLayoutEffect(()=>{
    const stopHeader=observeHeader(shell.current,header.current);
    scroller.current=createPublicScroller({main:main.current,header:header.current,navigate:to=>navigation.current(to)});
    return()=>{stopHeader();scroller.current.dispose();scroller.current=null;};
  },[]);
  useLayoutEffect(()=>{scroller.current?.route(location,navigationType);},[location,navigationType]);
  const {enabled}=useBookingProduct();
  useEffect(() => {
    writePageMetadata(document,location.pathname);
  }, [location.pathname]);

  return (
    <div className="sarsa-site" ref={shell}>
      <div>
        <div>
          <SiteHeader headerRef={header} sticky={location.pathname==='/booking'} />
          <a className="sarsa-skip" href="#page-content">Skip to content</a>
          <main id="page-content" ref={main} tabIndex="-1" className="flex-grow relative z-10">
            <Suspense fallback={<section className="sarsa-page-loading" aria-busy="true"><p role="status">Loading the page…</p></section>}><Routes>
              <Route path="/" element={<Home />} />
              <Route path="/about" element={<About />} />
              <Route path="/services/kundli-prediction" element={<KundliPrediction />} />
              <Route path="/services/prashna-kundali" element={<PrashnaKundali />} />
              <Route path="/services/:serviceId" element={<ServiceDetail />} />
              <Route path="/services" element={<Services />} />
              <Route path="/booking" element={<BookingRoute><Booking headerRef={header} /></BookingRoute>} />
              <Route path="/testimonials" element={<Testimonials />} />
              <Route path="/booking/receipt" element={<BookingRoute><BookingReceipt/></BookingRoute>}/>
              <Route path="/booking-help" element={<BookingRoute><BookingAccess/></BookingRoute>}/>
              <Route path="/contact" element={<ContactPage />} />
              {["privacy","terms","booking-policy"].map(policy=><Route key={policy} path={"/"+policy} element={policy==='booking-policy' && !enabled ? <UnavailablePage />:<PolicyPage policy={policy}/>} />)}
            <Route path="*" element={<section className="p-8"><h1>Page not found</h1><p>We couldn’t find that page.</p><a href="/">Return home</a> · <a href="/contact">Contact the practice</a></section>} /></Routes></Suspense>
          </main>
        </div>
      </div>
      <SiteFooter home={location.pathname==='/'} showBackToTop={['/','/testimonials'].includes(location.pathname)} scrollerRef={scroller} />
    </div>
  )
}

function App() {

  return (
    <Router>
      <ProductNavigationCheck />
      <AppShell />
    </Router>
  )
}

export default App
