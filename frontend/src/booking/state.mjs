export function reducer(state, action) {
  switch (action.type) {
    case 'policy': return { ...state, policy:action.value, loadingPolicy:false };
    case 'policy-error': return { ...state, loadingPolicy:false, error:action.message };
    case 'edit': {
      if (state.credential) return state;
      const next = { ...state, [action.name]:action.value, ack:false, error:'' };
      if (['service','day'].includes(action.name)) Object.assign(next, { slot:null, slots:[], slotsStatus:'idle' });
      return next;
    }
    case 'details': return state.credential ? state : { ...state, details:{...state.details, [action.name]:action.value}, ack:false };
    case 'slots-loading': return { ...state, slotsStatus:'loading', slots:[] };
    case 'slots': return action.service !== state.service || action.day !== state.day ? state
      : { ...state, slots:action.value.slots, slotsStatus:'ready', slot:action.value.slots.find(slot => slot.starts_at === state.slot?.starts_at) || null };
    case 'slots-error': return action.service !== state.service || action.day !== state.day ? state
      : { ...state, slots:[], slotsStatus:'error', error:action.message };
    case 'ack': return { ...state, ack:action.value };
    case 'busy': return { ...state, busy:action.value };
    case 'lock': return { ...state, credential:action.value, phase:'checking', error:'' };
    case 'receipt': return { ...state, receipt:action.value, phase:'receipt', error:'' };
    case 'modal': return { ...state, phase:'payment' };
    case 'error': return { ...state, error:action.message, retryAt:action.retryAt || 0 };
    case 'rejected': return { ...state, credential:null, receipt:null, phase:'draft', ack:false, retryAt:0, error:action.message || '' };
    case 'reset': return { ...state, credential:null, receipt:null, phase:'draft', ack:false, slot:null, slots:[], slotsStatus:'idle', error:action.message || '' };
    default: return state;
  }
}
