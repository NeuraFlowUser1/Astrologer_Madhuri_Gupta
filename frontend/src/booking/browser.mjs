import {createBookingBrowser} from '../../../appointment-system/browser/booking/index.mjs';
import {productState} from '../site/product-state.mjs';
import profile from '../../../appointment-settings/booking-browser.json';
export const bookingBrowser=createBookingBrowser(profile,{product:productState});
