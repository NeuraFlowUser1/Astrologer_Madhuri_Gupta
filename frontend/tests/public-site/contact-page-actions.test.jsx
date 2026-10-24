/** Page-owned action/rail contracts, isolated from booking-admission tests. */
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,Link,useLocation} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';

const model=vi.hoisted(()=>({enabled:true,location:null}));
vi.mock('../../src/site/BookingProduct.jsx',()=>({
  useBookingProduct:()=>model,
  BookingOnly:({children})=>model.enabled?children:null,
  BookingLink:({children,bookingMode:_mode,...props})=><Link {...props}>{children}</Link>,
  BookingAnchor:({children,bookingMode:_mode,...props})=><a {...props}>{children}</a>,
  BookingButton:({children,...props})=><button type="button" {...props}>{children}</button>,
}));
vi.mock('../../src/contact/motion.mjs',()=>({mountContactMotion:()=>()=>{}}));
vi.mock('../../src/contact/useEnquiry.jsx',()=>({useEnquiry:()=>({started:false,busy:false,blocked:false,retry:null,waiting:0,receipt:null})}));
import ContactPage from '../../src/pages/ContactPage.jsx';

let host,root;
function Location(){model.location=useLocation();return null;}
async function render(){await act(async()=>root.render(<MemoryRouter><ContactPage/><Location/></MemoryRouter>));}
beforeEach(async()=>{
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;model.enabled=true;
  host=document.createElement('div');document.body.append(host);root=createRoot(host);
  window.scrollTo=vi.fn();HTMLElement.prototype.scrollIntoView=vi.fn();
  vi.stubGlobal('matchMedia',()=>({matches:true}));await render();
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();delete HTMLElement.prototype.scrollIntoView;});

test('every page-owned booking invitation still navigates after rail/contact additions',async()=>{
  for(const selector of ['.hero [data-book]','.booking-lane','.margin-book','.weave-copy [data-book]']){
    await act(async()=>host.querySelector(selector).click());
    expect(model.location.pathname).toBe('/booking');
    expect(window.scrollTo).toHaveBeenLastCalledWith(0,0);
  }
  expect(host.querySelectorAll('.stage')).toHaveLength(5);
  expect(host.querySelectorAll('.answer-row')).toHaveLength(4);
  expect(host.querySelector('.contact-location a[href="tel:+918881573437"]')).not.toBeNull();
});

test('existing-booking help while OFF selects its topic and respects reduced motion',async()=>{
  model.enabled=false;await render();
  await act(async()=>host.querySelector('[data-route="existing"]').click());
  expect(host.querySelector('#topic').value).toBe('Existing booking');
  expect(HTMLElement.prototype.scrollIntoView).toHaveBeenLastCalledWith({behavior:'instant'});
  expect(host.querySelector('.contact-alternatives a[href="tel:+918881573437"]')).not.toBeNull();
  expect(host.querySelectorAll('.answer-row')).toHaveLength(3);
});
