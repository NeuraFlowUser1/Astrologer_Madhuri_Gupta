import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {test,expect,vi} from 'vitest';
const model=vi.hoisted(()=>({enabled:true,verified:true}));
vi.mock('../../src/site/BookingProduct.jsx',async()=>{const {Link}=await import('react-router-dom');return {BookingCopy:({children,off})=>model.enabled?children:off,BookingNavigationLink:({to,children,...props})=>model.enabled?<Link to={to} {...props}>{children}</Link>:null,useBookingProduct:()=>model,BookingOnly:({children})=>model.enabled?children:null,BookingLink:({to,bookingMode,children,...props})=>!model.enabled&&bookingMode==='hide'&&to.startsWith('/booking')?null:<Link to={!model.enabled&&to.startsWith('/booking')?'/contact':to} {...props}>{children}</Link>,BookingAnchor:({href,bookingMode:_bookingMode,children,...props})=>!model.enabled&&href.startsWith('/booking')?null:<a href={href} {...props}>{children}</a>,BookingButton:({bookingMode:_bookingMode,children,...props})=>model.enabled?<button {...props}>{children}</button>:null};});
vi.mock('../../src/contact/useEnquiry.jsx',()=>({useEnquiry:()=>({started:false,busy:false,blocked:false,retry:null,waiting:0,receipt:null})}));
import Home from '../../src/pages/Home.jsx';
import About from '../../src/pages/About.jsx';
import Services from '../../src/pages/Services.jsx';
import KundliPrediction from '../../src/pages/KundliPrediction.jsx';
import ServiceDetail from '../../src/pages/ServiceDetail.jsx';
import ContactPage from '../../src/pages/ContactPage.jsx';
import PolicyPage from '../../src/pages/PolicyPage.jsx';
function render(node,path='/'){const host=document.createElement('div');host.innerHTML=renderToStaticMarkup(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);return host;}
test.each([['Home',Home,'A little clarity.'],['About',About,'Every story'],['Services',Services,'Different questions.'],['Prediction',KundliPrediction,'Your questions.'],['Contact',ContactPage,'A question is']])('%s restores the selected checkpoint composition',(_name,Page,title)=>{const host=render(<Page/>);expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelector('h1').textContent).toContain(title);expect(host.querySelectorAll('section').length).toBeGreaterThanOrEqual(_name==='Services'?3:4);expect(host.querySelector('[data-motion]')).toBeNull();expect(host.querySelector('.sarsa-motion-scene')).toBeNull();});
test.each(['kundli-matching','vastu-consultation','numerology'])('service %s keeps its route and booking handoff',id=>{const host=render(<Routes><Route path="/services/:serviceId" element={<ServiceDetail/>}/></Routes>,'/services/'+id);expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelector(`a[href="/booking?service=${id}"]`)).not.toBeNull();});
test.each(['privacy','terms','booking-policy'])('policy %s remains reachable',policy=>{const host=render(<PolicyPage policy={policy}/>);expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.textContent.length).toBeGreaterThan(400);});
test('OFF preserves the enquiry form and removes booking entry points',()=>{model.enabled=false;try{for(const Page of [Home,About,Services,ContactPage]){const host=render(<Page/>);expect(host.querySelector('a[href^="/booking"]')).toBeNull();if(Page===ContactPage)expect(host.querySelector('#visitor-name')).not.toBeNull();}}finally{model.enabled=true;}});
