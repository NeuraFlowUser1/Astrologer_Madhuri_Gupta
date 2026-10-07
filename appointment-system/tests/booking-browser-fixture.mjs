export const installation_id='991c0e85-4f14-4b18-850b-acab0d4d6da4';
export const epoch='06960bb4-57a1-4af4-8265-f3da129c4af7';
export const now=Date.parse('2026-10-03T05:00:00Z');
export const starts='2026-10-03T06:00:00+00:00';
export const ends='2026-10-03T06:30:00+00:00';
export const service={id:'consultation',name:'Consultation',enabled:true,duration_minutes:30,
 pricing:{kind:'fixed',amount_paise:210000,maximum_questions:1},required_preparation:[]};
export const policy=()=>({policy:{version:1,timezone:'Asia/Kolkata',horizon_days:10,services:[structuredClone(service)],
 booking_verification:{email:false,sms:false},required_contacts:['phone'],meeting:'google_meet'},
 booking_verification_policy_hash:'b'.repeat(64),quote_version:'a'.repeat(64),server_now:new Date(now).toISOString(),schedule_browsing_open:true,
 receipt_access:{version:1,key_id:'current'}});
export const availability=(p=policy(),questions=1)=>({date:'2026-10-03',server_now:p.server_now,slots:[{starts_at:starts,ends_at:ends}],
 service:{...p.policy.services[0],questions,amount_paise:questions*210000,currency:'INR',timezone:p.policy.timezone,quote_version:p.quote_version}});
export const receipt=id=>({request_id:id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',
 service_name:'Consultation',currency:'INR',timezone:'Asia/Kolkata',amount_paise:210000,captured_paise:0,refunded_paise:0,
 starts_at:starts,ends_at:ends,server_now:new Date(now).toISOString(),hold_expires_at:new Date(now+900000).toISOString(),
 next_actions:['check_status','check_payment'],meeting_state:'not_created',meet_url:null});
export const checkout=id=>({receipt:{...receipt(id),next_actions:['resume_payment','check_status']},checkout:{
 key_id:'rzp_live_synthetic',order_id:'order_fixture',amount_paise:210000,currency:'INR'}});
