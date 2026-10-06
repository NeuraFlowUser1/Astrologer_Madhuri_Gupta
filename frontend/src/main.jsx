import {productState} from './site/product-state.mjs';
import {startWhenBookingOn} from '../../appointment-system/browser/conditional-work.mjs';
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import {migrateLegacyLocation} from './site/routes.mjs'
migrateLegacyLocation(window.location,window.history)

async function mountWebsite(){
// State is proved before any booking component mounts; failure starts safely off.
await productState.refresh({force:true});
productState.start();
startWhenBookingOn(()=>import('./booking/browser.mjs').then(({bookingBrowser})=>()=>bookingBrowser.recovery.start()));
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
}
mountWebsite();
