import {productState} from './site/product-state.mjs';
import {startWhenBookingOn} from '../../appointment-system/browser/conditional-work.mjs';
import React from 'react';
import {createRoot,hydrateRoot} from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import {migrateLegacyLocation} from './site/routes.mjs';
migrateLegacyLocation(window.location,window.history);
const container=document.getElementById('root');
const tree=<React.StrictMode><App/></React.StrictMode>;
const generated=container.dataset.publicPath===window.location.pathname&&container.dataset.publicRender==='sarsa-public-v1';
// Keep generated public content in place while the signed live check runs.
if(generated)hydrateRoot(container,tree,{identifierPrefix:'sarsa-public-'});
else createRoot(container,{identifierPrefix:'sarsa-public-'}).render(tree);
const booking=/^\/booking(?:\/|$)|^\/booking-help$|^\/booking-policy$/.test(window.location.pathname);
productState.start(window,document,{profile:booking?'active':'public',refreshOnStart:false});
void productState.refresh({force:true});
startWhenBookingOn(()=>import('./booking/browser.mjs').then(({bookingBrowser})=>()=>bookingBrowser.recovery.start()),{state:productState});
