import * as React from 'react';
import * as Router from 'react-router-dom';
import {createReactBindings} from '../../../appointment-system/browser/react-bindings.mjs';
import {surfaces} from '../../../appointment-settings/project.json';
export const {useBookingProduct,ProductNavigationCheck,BookingOnly,BookingCopy,BookingLink,BookingAnchor,BookingButton,UnavailablePage,BookingRoute,BookingNavigationLink}=createReactBindings(React,Router,{surfaces});
