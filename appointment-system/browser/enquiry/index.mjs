import {createEnquiryAPI} from './protocol.mjs';
import {createEnquiryStore} from './credentials.mjs';
import {createEnquiryController} from './controller.mjs';
import {RequestError} from '../transport.mjs';

export function createEnquiryBrowser(profile,{storage=()=>window.sessionStorage,fetcher=globalThis.fetch}={}){
 if(!profile || Object.keys(profile).sort().join(',')!=='channels,environment,installation_id,version' || profile.version!==1
  || !profile.channels || typeof profile.channels!=='object' || Array.isArray(profile.channels)
  || Object.keys(profile.channels).length<1 || Object.keys(profile.channels).length>8)throw new RequestError('invalid_configuration');
 const channels=new Map();
 for(const [channel,settings] of Object.entries(profile.channels)){
  if(!settings || Object.keys(settings).join(',')!=='legacy_receipts')throw new RequestError('invalid_configuration');
  channels.set(channel,createEnquiryStore({...profile,...settings,channel}));
 }
 const api=createEnquiryAPI({fetcher});
 return Object.freeze({controller(channel='contact'){
  if(!channels.has(channel))throw new RequestError('invalid_configuration');
  return createEnquiryController({api,receipts:channels.get(channel),storage});
 }});
}

/** React is supplied by the containing website; all workflow decisions stay shared. */
export function createUseEnquiry(React,browser){
 return function useEnquiry(channel='contact'){
  const controller=React.useMemo(()=>browser.controller(channel),[channel]);
  const state=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  React.useEffect(()=>controller.start(),[controller]);
  return {...state,start:controller.submit,check:controller.check,verify:controller.verify,resend:controller.resend,
   retryRequest:controller.retryRequest,restart:controller.restart};
 };
}
