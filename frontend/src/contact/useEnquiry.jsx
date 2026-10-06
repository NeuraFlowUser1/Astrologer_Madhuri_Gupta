import * as React from 'react';
import {createEnquiryBrowser,createUseEnquiry} from '../../../appointment-system/browser/enquiry/index.mjs';
import profile from '../../../appointment-settings/enquiry-browser.json';
export const useEnquiry=createUseEnquiry(React,createEnquiryBrowser(profile));
