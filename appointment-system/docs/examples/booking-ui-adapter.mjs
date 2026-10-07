// Copy into the project's frontend. Adjust only the contained-package paths,
// local bookingBrowser import, practice name and theme. Install the four pinned peers.
import * as React from 'react';
import {DatePicker,TimeField,DateInput,DateSegment,Label,Group,Button,Popover,Dialog,Calendar,
 CalendarGrid,CalendarCell,Heading,Text,FieldError,I18nProvider} from 'react-aria-components';
import {parseDate,parseTime,Time} from '@internationalized/date';
import {createDateTimeFields} from '../appointment-system/browser/booking/date-time-fields.mjs';
import {createReceiptFields} from '../appointment-system/browser/booking/receipt-fields.mjs';
import '../appointment-system/browser/booking/date-time-fields.css';
import '../appointment-system/browser/booking/receipt-fields.css';
import {bookingBrowser} from './bookingBrowser.mjs';

export const {DateField,TimeField:BirthTimeField}=createDateTimeFields(React,{DatePicker,TimeField,DateInput,DateSegment,
 Label,Group,Button,Popover,Dialog,Calendar,CalendarGrid,CalendarCell,Heading,Text,FieldError,I18nProvider,parseDate,parseTime,Time});
let dependencies;
async function loadPDF(){
 if(!dependencies)dependencies=Promise.all([import('pdf-lib'),import('@pdf-lib/fontkit'),(async()=>{
  const response=await fetch(new URL('../appointment-system/browser/booking/receipt-assets/source-sans-3-regular.ttf',import.meta.url),
   {redirect:'error',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('pdf_unavailable');const buffer=await response.arrayBuffer();
  if(!buffer.byteLength || buffer.byteLength>1048576)throw Error('pdf_unavailable');return new Uint8Array(buffer);
 })()]).then(([pdf,fontkit,fontBytes])=>({...pdf,fontkit:fontkit.default,fontBytes})).catch(error=>{dependencies=null;throw error;});
 return dependencies;
}
export const ReceiptFields=createReceiptFields(React,{browser:bookingBrowser,brand:'YOUR PRACTICE NAME',loadPDF,theme:''});
