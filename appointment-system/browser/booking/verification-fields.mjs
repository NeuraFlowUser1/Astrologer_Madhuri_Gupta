/** Presentation only. The shared coordinator owns challenge and grant decisions. */
export function createVerificationFields(React){
 const {createElement:h,useState,useEffect}=React;
 return function VerificationFields({flow,className='field',inputClassName='',buttonClassName='button'}){
  const [code,setCode]=useState(''),[now,setNow]=useState(Date.now()),{state}=flow;
  useEffect(()=>{setCode('');},[state.challenge?.challenge_id,state.challenge?.generation,state.details.email]);
  const expiry=Date.parse(state.verification?.expires_at||state.challenge?.expires_at||'')-(state.serverOffset||0);
  useEffect(()=>{
   const future=[state.retryAt,expiry].filter(value=>Number.isFinite(value)&&value>Date.now());
   if(!future.length)return;
   const timer=setTimeout(()=>setNow(Date.now()),Math.min(...future)-Date.now()+10);return()=>clearTimeout(timer);
  },[state.retryAt,expiry,now]);
  if(!state.policy?.policy.booking_verification.email || state.credential)return null;
  if(state.verification && expiry>Date.now())return h('p',{role:'status'},'Your email address is verified.');
  const waiting=state.busy || !state.policyFresh || flow.available===false || Date.now()<state.retryAt;
  return h('div',{className},
   h('p',null,'Verify your email address before continuing to payment.'),
   !state.challenge || expiry<=Date.now()?h('button',{type:'button',className:buttonClassName,disabled:waiting||!state.details.email,onClick:flow.startVerification},state.challenge?'Request a new code':'Send email code'):
    h(React.Fragment,null,h('label',null,'Email verification code',h('input',{className:inputClassName,type:'text',inputMode:'numeric',autoComplete:'one-time-code',
     value:code,maxLength:6,pattern:'[0-9]{6}',onChange:event=>setCode(event.target.value.replace(/[^0-9]/g,'')),disabled:waiting})),
     h('button',{type:'button',className:buttonClassName,disabled:waiting||code.length!==6,onClick:()=>flow.verifyCode(code)},'Verify code'),
     h('button',{type:'button',className:buttonClassName,disabled:waiting||state.challenge.generation>=3,onClick:flow.resendVerification},'Send another code')));
 };
}
