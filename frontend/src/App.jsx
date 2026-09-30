import React, { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, useLocation, Navigate } from 'react-router-dom'
import {pages,origin,titleFor} from './site/page-metadata.mjs'
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
  useEffect(() => {
    const path=location.pathname, data=pages[path];
    document.title=titleFor(path);
    for(const selector of ['meta[name="title"]','meta[property="og:title"]','meta[name="twitter:title"]']) document.querySelector(selector)?.setAttribute('content',titleFor(path));
    for(const selector of ['meta[name="description"]','meta[property="og:description"]','meta[name="twitter:description"]']) document.querySelector(selector)?.setAttribute('content',data?.[1]||'We could not find that page.');
    document.querySelector('link[rel="canonical"]')?.setAttribute('href',origin+path);
    for(const selector of ['meta[property="og:url"]','meta[name="twitter:url"]']) document.querySelector(selector)?.setAttribute('content',origin+path);
    document.querySelector('meta[name="robots"]')?.setAttribute('content',data?'index, follow':'noindex');
  }, [location.pathname]);
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
              <Route path="/booking" element={<Booking />} />
              <Route path="/testimonials" element={<Navigate to="/about" replace />} />
              <Route path="/contact" element={<ContactPage />} />
              {["privacy","terms","booking-policy"].map(policy=><Route key={policy} path={"/"+policy} element={<PolicyPage policy={policy}/>} />)}
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
      <ScrollToHashElement />
      <AppShell />
    </Router>
  )
}

export default App
