import React, { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, useLocation, Navigate } from 'react-router-dom'
import {pages,origin,titleFor} from './site/page-metadata.mjs'
import {useBookingProduct,ProductNavigationCheck,UnavailablePage,BookingRoute} from './site/BookingProduct.jsx'
const BookingReceipt = lazy(() => import('./pages/BookingReceipt.jsx'))
const BookingAccess = lazy(() => import('./pages/BookingAccess.jsx'))
import {SiteHeader,SiteFooter} from './site/SiteFrame.jsx'
const KundliPrediction = lazy(() => import('./pages/KundliPrediction.jsx'))
const ServiceDetail = lazy(() => import('./pages/ServiceDetail.jsx'))
const PolicyPage = lazy(() => import('./pages/PolicyPage.jsx'))
const Home = lazy(() => import('./pages/Home.jsx'))
const About = lazy(() => import('./pages/About.jsx'))
const Services = lazy(() => import('./pages/Services.jsx'))
const Booking = lazy(() => import('./pages/Booking.jsx'))
const ContactPage = lazy(() => import('./pages/ContactPage.jsx'))

function AppShell() {
  const location = useLocation()
  const {enabled}=useBookingProduct();
  useEffect(() => {
    const path=location.pathname, data=pages[path];
    const description=!enabled ? ({'/':'Explore astrology, Numerology and Vastu guidance with Madhuri Gupta. Contact the practice with your questions.','/services':'Explore Kundli Prediction, Kundli Matching, Vastu and Numerology guidance. Contact the practice with your questions.','/contact':'Send the practice a question or ask for help with an existing booking.'}[path] || data?.[1]):data?.[1];
    document.title=titleFor(path);
    for(const selector of ['meta[name="title"]','meta[property="og:title"]','meta[name="twitter:title"]']) document.querySelector(selector)?.setAttribute('content',titleFor(path));
    for(const selector of ['meta[name="description"]','meta[property="og:description"]','meta[name="twitter:description"]']) document.querySelector(selector)?.setAttribute('content',description||'We could not find that page.');
    document.querySelector('link[rel="canonical"]')?.setAttribute('href',origin+path);
    for(const selector of ['meta[property="og:url"]','meta[name="twitter:url"]']) document.querySelector(selector)?.setAttribute('content',origin+path);
    document.querySelector('meta[name="robots"]')?.setAttribute('content',data && (enabled || !['/booking','/booking-policy'].includes(path)) ? 'index, follow':'noindex');
  }, [location.pathname,enabled]);
  const hasOwnNavigation = ['/booking', '/contact'].includes(location.pathname)

  return (
    <div className="sarsa-site">
      <div>
        <div>
          {!hasOwnNavigation && <SiteHeader />}
          <a className="sarsa-skip" href="#page-content">Skip to content</a>
          <main id="page-content" tabIndex="-1" className="flex-grow relative z-10">
            <Suspense fallback={<p role="status" className="p-8">Loading the page…</p>}><Routes>
              <Route path="/" element={<Home />} />
              <Route path="/about" element={<About />} />
              <Route path="/services/kundli-prediction" element={<KundliPrediction />} />
              <Route path="/services/:serviceId" element={<ServiceDetail />} />
              <Route path="/services" element={<Services />} />
              <Route path="/booking" element={<BookingRoute><Booking /></BookingRoute>} />
              <Route path="/testimonials" element={<Navigate to="/about" replace />} />
              <Route path="/booking/receipt" element={<BookingRoute><BookingReceipt/></BookingRoute>}/>
              <Route path="/booking-help" element={<BookingRoute><BookingAccess/></BookingRoute>}/>
              <Route path="/contact" element={<ContactPage />} />
              {["privacy","terms","booking-policy"].map(policy=><Route key={policy} path={"/"+policy} element={policy==='booking-policy' && !enabled ? <UnavailablePage />:<PolicyPage policy={policy}/>} />)}
            <Route path="*" element={<section className="p-8"><h1>Page not found</h1><p>We couldn’t find that page.</p><a href="/">Return home</a> · <a href="/contact">Contact the practice</a></section>} /></Routes></Suspense>
          </main>
        </div>
      </div>
      {!hasOwnNavigation && <SiteFooter />}
    </div>
  )
}

function ScrollToHashElement() {
  const location = useLocation()

  useEffect(() => {
    if (!location.hash) { window.scrollTo(0, 0); return; }
    let elementId; try { elementId = decodeURIComponent(location.hash.substring(1)); } catch { return; }
    let observer, timer;
    const scroll = () => {
      const el = document.getElementById(elementId);
      if (!el) return false;
      el.scrollIntoView({behavior:'auto'});
      observer?.disconnect(); clearTimeout(timer); return true;
    };
    if (!scroll()) {
      observer = new MutationObserver(scroll);
      observer.observe(document.body,{childList:true,subtree:true});
      timer = setTimeout(() => observer.disconnect(),10000);
    }
    return () => { observer?.disconnect(); clearTimeout(timer); };
  }, [location.pathname, location.hash]);

  return null
}

function App() {

  return (
    <Router>
      <ScrollToHashElement /><ProductNavigationCheck />
      <AppShell />
    </Router>
  )
}

export default App
