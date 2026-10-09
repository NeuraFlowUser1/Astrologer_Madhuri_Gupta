import {createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import {Link,useLocation,useNavigate} from 'react-router-dom';
import {moveToTarget,waitForTarget} from './anchor-navigation.mjs';
import {usePublicHeader} from './PublicHeaderContext.jsx';

const AnchorContext=createContext(null);
export function AnchorNavigationProvider({children}){
 const location=useLocation(),navigate=useNavigate(),bar=usePublicHeader();
 const pending=useRef(null),cancel=useRef(()=>{}),sequence=useRef(0);
 const [request,setRequest]=useState(0);
 const activate=useCallback((to,options={})=>{
  cancel.current();pending.current={to,options};setRequest(++sequence.current);
  if(to!==location.pathname+location.hash)navigate(to);
 },[location.pathname,location.hash,navigate]);
 useEffect(()=>{
  const path=location.pathname+location.hash;
  const intent=pending.current?.to===path?pending.current:null;
  if(intent)pending.current=null;
  cancel.current();
  if(!location.hash){window.scrollTo({top:0,behavior:'instant'});return;}
  let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
  // Targets must be existing IDs on this page, never markup or redirects.
  if(!/^[a-z][a-z0-9-]{0,79}$/i.test(id))return;
  cancel.current=waitForTarget(id,node=>moveToTarget({target:node,header:bar?.current,
   smooth:!!intent&&id!=='page-content',focus:intent?.options.focus||(()=>id==='consultations'?document.querySelector('#starting-point h2'):node.matches('h1,h2,h3,main')?node:node.querySelector('h1,h2,h3')||node)}));
  return()=>cancel.current();
 },[location.pathname,location.hash,request,bar]);
 useEffect(()=>()=>cancel.current(),[]);
 return <AnchorContext.Provider value={activate}>{children}</AnchorContext.Provider>;
}
export function useAnchorNavigation(){return useContext(AnchorContext);}
export function AnchorLink({to,onClick,focus,children,...props}){
 const activate=useAnchorNavigation();
 return <Link to={to} {...props} onClick={event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||props.target||props.download!==undefined)return;
  onClick?.(event);if(event.defaultPrevented)return;
  event.preventDefault();activate(to,{focus});
 }}>{children}</Link>;
}
