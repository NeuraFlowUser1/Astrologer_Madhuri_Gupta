/** Shared display formatting; no booking requests, credentials or state. */
export const localDate=(value=new Date(),timezone='Asia/Kolkata')=>new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
export const money=paise=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:paise%100?2:0}).format(paise/100);
export const appointmentLabel=(value,timezone='Asia/Kolkata')=>new Intl.DateTimeFormat('en-IN',{timeZone:timezone,dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
export const timeLabel=(value,timezone='Asia/Kolkata')=>new Intl.DateTimeFormat('en-IN',{timeZone:timezone,hour:'numeric',minute:'2-digit'}).format(new Date(value));
export function dateRange(policy){
 const first=localDate(policy.server_now,policy.policy.timezone),last=new Date(first+'T12:00:00Z');
 last.setUTCDate(last.getUTCDate()+policy.policy.horizon_days);
 return {first_date:first,last_date:last.toISOString().slice(0,10),timezone:policy.policy.timezone};
}
