/** Framework primitives come from the project's React copy; no second React. */
import {classify,normalizedPath} from '../hosting/surface-policy.mjs';
import {productState as defaultState} from './product-state.mjs';

export function createReactBindings(React,Router,{surfaces,state=defaultState,contactPath='/contact'}={}){
 const {createElement:h,useEffect,useSyncExternalStore}=React;
 const {Link,useLocation,useNavigate}=Router;
 const useBookingProduct=()=>useSyncExternalStore(state.subscribe,state.getSnapshot,state.getServerSnapshot);
 const bookingTarget=target=>{
  if(typeof target!=='string' || !target.startsWith('/') || target.startsWith('//'))return false;
  try{return classify(normalizedPath(decodeURIComponent(target.split(/[?#]/)[0])),surfaces)==='booking';}catch{return false;}
 };
 function ProductNavigationCheck(){
  const location=useLocation();useEffect(()=>state.start(),[]);
  useEffect(()=>{void state.refresh();},[location.pathname]);return null;
 }
 function BookingOnly({children}){return useBookingProduct().enabled?children:null;}
 function BookingCopy({children,off}){return useBookingProduct().enabled?children:off;}
 function BookingLink({children,bookingMode,offText='Send an enquiry',to,...props}){
  const {enabled}=useBookingProduct(),off=bookingTarget(to) && !enabled;
  if(off && bookingMode==='hide')return null;
  return h(Link,{...props,to:off?contactPath:to,'aria-label':off?offText:props['aria-label']},off?offText:children);
 }
 function BookingAnchor({children,bookingMode,offText='Send an enquiry',href,...props}){
  const {enabled}=useBookingProduct(),off=bookingTarget(href) && !enabled;
  if(off && bookingMode==='hide')return null;
  return h('a',{...props,href:off?contactPath:href,'aria-label':off?offText:props['aria-label']},off?offText:children);
 }
 function BookingButton({children,bookingMode,offText='Send an enquiry',offPath=contactPath,onClick,...props}){
  const {enabled}=useBookingProduct(),navigate=useNavigate();
  if(!enabled && bookingMode==='hide')return null;
  return h('button',{type:'button',...props,onClick:event=>{
   // Read the current store at click time, not an older render's ON value.
   if(!state.getSnapshot().enabled){event.preventDefault();event.stopPropagation();navigate(offPath);}else onClick?.(event);
  }},enabled?children:offText);
 }
 function UnavailablePage(){return h('section',{className:'p-8'},h('h1',null,'Page not found'),
  h('p',null,'Contact the practice if you need help.'),h(Link,{to:contactPath},'Send an enquiry'));}
 function BookingRoute({children}){return useBookingProduct().enabled?children:h(UnavailablePage);}
 function BookingNavigationLink(props){return h(BookingLink,{...props,bookingMode:'hide'});}
 return {useBookingProduct,ProductNavigationCheck,BookingOnly,BookingCopy,BookingLink,BookingAnchor,BookingButton,
  UnavailablePage,BookingRoute,BookingNavigationLink};
}
