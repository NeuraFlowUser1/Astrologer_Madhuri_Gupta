import {serviceState} from './service-state.mjs';
import {recoveryFetch,scheduled,queue} from './recovery.mjs';
export {BookingProductState} from './service-state.mjs';
export {BookingRecoveryState} from './recovery.mjs';
export default {
  scheduled,
  queue,
  async fetch(request,env) {
    const response=await serviceState(request,env);
    return response || await recoveryFetch(request,env) || Response.json({code:'not_found'},{status:404,headers:{'cache-control':'no-store'}});
  }
};
