/** Framework primitives come from the project's React copy; no second React. */
import {classify,normalizedPath} from '../hosting/surface-policy.mjs';
import {productState as defaultState,displayAllowed,admissionAllowed,retainView} from './product-state.mjs';

export function createReactBindings(React,Router,{surfaces,state=defaultState,contactPath='/contact',lifecycleOwner='bindings'}={}){
 if(!['bindings','entry'].includes(lifecycleOwner))throw TypeError('Invalid display lifecycle owner.');
 const {createElement:h,useEffect,useRef,useSyncExternalStore,useContext,createContext}=React;
 const {Link,useLocation,useNavigate}=Router;
 const Context=createContext(null),intents=new WeakMap();
 const useStore=()=>useContext(Context)||state;
 const useBookingProduct=()=>{const store=useStore();return useSyncExternalStore(store.subscribe,store.getSnapshot,store.getServerSnapshot);};
 function BookingStateProvider({controller,children}){
  if(!controller || typeof controller.getSnapshot!=='function')throw TypeError('A display controller is required.');
  return h(Context.Provider,{value:controller},children);
 }
 const bookingTarget=target=>{
  if(typeof target!=='string' || !target.startsWith('/') || target.startsWith('//'))return false;
  try{return classify(normalizedPath(decodeURIComponent(target.split(/[?#]/)[0])),surfaces)==='booking';}catch{return false;}
 };
 function ProductNavigationCheck(){
  const location=useLocation(),store=useStore();
  useEffect(()=>lifecycleOwner==='bindings'?store.start():undefined,[store]);
  useEffect(()=>{
   intents.set(store,(intents.get(store)||0)+1);
   store.setProfile(bookingTarget(location.pathname)?'active':'public');
   void store.refresh();
  },[store,location.pathname]);return null;
 }
 /** One current entry intent per store; another route/entry makes a slow reply harmless. */
 function useEntry(){
  const store=useStore(),navigate=useNavigate(),location=useLocation(),pending=useRef(null);
  useEffect(()=>()=>{
   if(pending.current && intents.get(store)===pending.current.generation)intents.set(store,pending.current.generation+1);
   pending.current=null;
  },[store,location.pathname,location.search]);
  return (destination,action,fallback=contactPath)=>{
   if(pending.current && pending.current.destination===destination)return pending.current.promise;
   const generation=(intents.get(store)||0)+1;intents.set(store,generation);
   const origin=location.pathname+(location.search||'');
   const current=()=>intents.get(store)===generation &&
    (typeof window==='undefined' || window.location.pathname+window.location.search===origin);
   const work=async()=>{
    try{
     await store.refresh({force:true});if(!current())return;
     if(!admissionAllowed(store.getSnapshot())){navigate(fallback);return;}
     if(action)action();else navigate(destination);
    }catch{if(current())navigate(fallback);}
    finally{if(pending.current?.promise===promise)pending.current=null;}
   };
   const promise=Promise.resolve().then(work);pending.current={promise,destination,generation};return promise;
  };
 }
 const plainClick=(event,props)=>!event.defaultPrevented && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
  && (event.button===undefined || event.button===0) && (!props.target || props.target==='_self')
  && !(Object.hasOwn(props,'download') && props.download!==false);
 function BookingOnly({children}){return displayAllowed(useBookingProduct())?children:null;}
 function BookingCopy({children,off}){return displayAllowed(useBookingProduct())?children:off;}
 function BookingLink({children,bookingMode,offText='Send an enquiry',to,...props}){
  const current=useBookingProduct(),entry=useEntry(),off=bookingTarget(to) && !displayAllowed(current);
  if(off && bookingMode==='hide')return null;
  return h(Link,{...props,to:off?contactPath:to,'aria-label':off?offText:props['aria-label'],onClick:event=>{
   props.onClick?.(event);
   if(bookingTarget(to) && !off && plainClick(event,props)){event.preventDefault();void entry(to);}
  }},off?offText:children);
 }
 function BookingAnchor({children,bookingMode,offText='Send an enquiry',href,...props}){
  const current=useBookingProduct(),entry=useEntry(),off=bookingTarget(href) && !displayAllowed(current);
  if(off && bookingMode==='hide')return null;
  return h('a',{...props,href:off?contactPath:href,'aria-label':off?offText:props['aria-label'],onClick:event=>{
   props.onClick?.(event);
   if(bookingTarget(href) && !off && plainClick(event,props)){event.preventDefault();void entry(href);}
  }},off?offText:children);
 }
 function BookingButton({children,bookingMode,offText='Send an enquiry',offPath=contactPath,onClick,...props}){
  const current=useBookingProduct(),enabled=displayAllowed(current),navigate=useNavigate(),entry=useEntry();
  if(!enabled && bookingMode==='hide')return null;
  return h('button',{type:'button',...props,onClick:event=>{
   event.preventDefault();event.stopPropagation?.();
   if(!enabled){navigate(offPath);return;}
   void entry(null,()=>onClick?.(event),offPath);
  }},enabled?children:offText);
 }
 function UnavailablePage(){return h('section',{className:'p-8'},h('h1',null,'Page not found'),
  h('p',null,'Contact the practice if you need help.'),h(Link,{to:contactPath},'Send an enquiry'));}
 function BookingRoute({children}){
  const current=useBookingProduct(),exposed=useRef(false);
  if(admissionAllowed(current))exposed.current=true;
  if(!retainView(current))exposed.current=false;
  const mounted=exposed.current && retainView(current),visible=mounted && displayAllowed(current);
  return h(React.Fragment,null,
   mounted?h('div',{className:'booking-retained-view',hidden:!visible,inert:!visible},children):null,
   visible?null:h(UnavailablePage));
 }
 function BookingNavigationLink(props){return h(BookingLink,{...props,bookingMode:'hide'});}
 return {BookingStateProvider,useBookingProduct,ProductNavigationCheck,BookingOnly,BookingCopy,BookingLink,BookingAnchor,BookingButton,
  UnavailablePage,BookingRoute,BookingNavigationLink};
}
