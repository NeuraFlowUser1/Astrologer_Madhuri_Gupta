import {RequestError} from '../transport.mjs';

const uuid=value=>typeof value==='string' && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(value);
const secrets={q1:/^q1\.[a-z0-9][a-z0-9_-]{0,31}\.[A-Za-z0-9_-]{43}$/,hex64:/^[a-f0-9]{64}$/,url43:/^[A-Za-z0-9_-]{43}$/};
const same=(a,b)=>a.request_id===b.request_id && a.secret===b.secret;
const fail=()=>{throw new RequestError('receipt_unavailable');};

/** Each enquiry channel owns its reference. Never stores form contents or email codes. */
export function createEnquiryStore({installation_id,environment,channel,legacy_receipts=[]}){
 if(typeof installation_id!=='string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(installation_id)
  || installation_id==='00000000-0000-0000-0000-000000000000' || !['production','development','test'].includes(environment)
  || !/^[a-z][a-z0-9-]{0,31}$/.test(channel || '') || !Array.isArray(legacy_receipts) || legacy_receipts.length>4)
  throw new RequestError('invalid_configuration');
 const key=`appointment:${installation_id}:${environment}:enquiry:${channel}:v1`;
 const readers=[{key,format:'current'}];
 for(const row of legacy_receipts){
  if(!row || Object.keys(row).sort().join(',')!=='format,key' || !['id-hex64','request-url43'].includes(row.format)
   || typeof row.key!=='string' || !/^[A-Za-z0-9:/_-]{1,120}$/.test(row.key) || readers.some(v=>v.key===row.key))
   throw new RequestError('invalid_configuration');
  readers.push({...row});
 }
 function parse(raw,format){
  let value;try{if(raw.length>4096)fail();value=JSON.parse(raw);}catch{fail();}
  if(!value || typeof value!=='object' || Array.isArray(value))fail();
  const fields=Object.keys(value),allowed=format==='current'
   ?['version','installation_id','environment','channel','credential_format','request_id','secret','resend_id','resend_generation']
   :format==='id-hex64'?['id','secret']:['version','request_id','secret','resend_id','resend_generation'];
  if(fields.some(v=>!allowed.includes(v)))fail();
  if(format==='current'){
   if(value.version!==1 || value.installation_id!==installation_id || value.environment!==environment || value.channel!==channel
     || !Object.hasOwn(secrets,value.credential_format))fail();
  }else if(format==='id-hex64')value={request_id:value.id,secret:value.secret,credential_format:'hex64'};
  else {if(value.version!==1)fail();value={...value,credential_format:'url43'};}
  if(!uuid(value.request_id) || typeof value.secret!=='string' || !secrets[value.credential_format].test(value.secret)
   || ((value.resend_id===undefined)!==(value.resend_generation===undefined))
   || (value.resend_id!==undefined && (!uuid(value.resend_id) || !Number.isInteger(value.resend_generation)
     || value.resend_generation<1 || value.resend_generation>2)))fail();
  return Object.freeze({request_id:value.request_id.toLowerCase(),secret:value.secret,credential_format:value.credential_format,
   ...(value.resend_id===undefined?{}:{resend_id:value.resend_id.toLowerCase(),resend_generation:value.resend_generation})});
 }
 function entries(storage){
  try{return readers.flatMap(reader=>{const raw=storage.getItem(reader.key);return raw===null?[]:[{key:reader.key,value:parse(raw,reader.format)}];});}
  catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
 }
 function read(storage){
  const values=entries(storage);if(values.some(v=>!same(v.value,values[0].value)))throw new RequestError('receipt_conflict');
  return values[0]?.value || null;
 }
 function save(storage,value){
  const current=read(storage);if(current && !same(current,value))throw new RequestError('receipt_conflict');
  const encoded=JSON.stringify({version:1,installation_id,environment,channel,...value});parse(encoded,'current');
  try{storage.setItem(key,encoded);if(storage.getItem(key)!==encoded)throw Error();}
  catch{throw new RequestError('storage_unavailable');}
  return read(storage);
 }
 function create(storage,policy,source=globalThis.crypto){
  if(policy?.version!==1 || !/^[a-z0-9][a-z0-9_-]{0,31}$/.test(policy.receipt_key_id || ''))throw new RequestError('invalid_response');
  if(read(storage))throw new RequestError('request_in_progress');
  const bytes=source.getRandomValues(new Uint8Array(32));
  return save(storage,{request_id:source.randomUUID(),credential_format:'q1',secret:'q1.'+policy.receipt_key_id+'.'+
   btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','')});
 }
 function clear(storage,expected){
  const values=entries(storage);
  if(!expected || !values.length || values.some(v=>!same(v.value,expected)))throw new RequestError('receipt_conflict');
  try{for(const value of values)storage.removeItem(value.key);if(read(storage))throw Error();}
  catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
 }
 return Object.freeze({read,save,create,clear,storageKey:key});
}
