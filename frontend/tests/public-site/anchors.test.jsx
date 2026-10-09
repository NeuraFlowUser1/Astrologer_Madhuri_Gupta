import React,{act,StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {test,expect,vi} from 'vitest';
import {PublicHeaderProvider} from '../../src/site/PublicHeaderContext.jsx';
import {AnchorNavigationProvider,AnchorLink} from '../../src/site/AnchorNavigation.jsx';
test('direct lazy anchors survive development setup-cleanup-setup and preserve modified clicks',async()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;window.scrollTo=vi.fn();vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener(){},removeEventListener(){}}));vi.stubGlobal('requestAnimationFrame',fn=>setTimeout(()=>fn(performance.now()+300),0));vi.stubGlobal('cancelAnimationFrame',clearTimeout);
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host),activate=vi.fn();
 try{await act(async()=>root.render(<StrictMode><MemoryRouter initialEntries={['/about#consultations']}><PublicHeaderProvider><AnchorNavigationProvider><div id="consultations"/><section id="starting-point"><h2 tabIndex={-1}>Choose a service</h2></section><AnchorLink to="/about#consultations" onClick={activate}>Return to services</AnchorLink><AnchorLink to="/about#bad%" download>Download</AnchorLink></AnchorNavigationProvider></PublicHeaderProvider></MemoryRouter></StrictMode>));await act(async()=>new Promise(resolve=>setTimeout(resolve,20)));expect(document.activeElement).toBe(host.querySelector('h2'));
 const link=host.querySelector('a');await act(async()=>link.dispatchEvent(new MouseEvent('click',{ctrlKey:true,bubbles:true,cancelable:true})));expect(activate).not.toHaveBeenCalled();await act(async()=>link.click());await act(async()=>new Promise(resolve=>setTimeout(resolve,20)));expect(activate).toHaveBeenCalledOnce();expect(document.activeElement).toBe(host.querySelector('h2'));
 }finally{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();}
});
