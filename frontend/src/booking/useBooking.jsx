import * as React from 'react';
import {createUseBooking} from '../../../appointment-system/browser/booking/index.mjs';
import {bookingBrowser} from './browser.mjs';
export const useBooking=createUseBooking(React,bookingBrowser);
