import {RequestError} from '../transport.mjs';
const uuid=value=>typeof value==='string' && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(value);
const keyId=/^[a-z0-9][a-z0-9_-]{0,31}$/;
const currentSecret=/^r1\.[a-z0-9][a-z0-9_-]{0,31}\.[A-Za-z0-9_-]{43}$/;
const equal=(left,right)=>left.request_id===right.request_id && left.secret===right.secret;

export function createReceiptStore({installation_id,environment,legacy_receipts=[]}){
 if(typeof installation_id!=='string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(installation_id)
  || installation_id==='00000000-0000-0000-0000-000000000000' || !['production','development','test'].includes(environment)
  || !Array.isArray(legacy_receipts) || legacy_receipts.length>4)throw new RequestError('invalid_configuration');
 const current=`appointment:${installation_id}:${environment}:booking:v1`,stageKey=current+':recovery';
 const readers=[{key:current,format:'v1'}];
 for(const row of legacy_receipts){
  if(!row || Object.keys(row).sort().join(',')!=='format,key' || !['id-hex64','request-url43'].includes(row.format)
    || typeof row.key!=='string' || !/^[A-Za-z0-9:_-]{1,120}$/.test(row.key) || readers.some(reader=>reader.key===row.key))
   throw new RequestError('invalid_configuration');
  readers.push({...row});
 }
 function parse(raw,format){
  let value;try{value=JSON.parse(raw);}catch{throw new RequestError('receipt_unavailable');}
  const fields=value && typeof value==='object' && !Array.isArray(value)?Object.keys(value).sort().join(','):'';
  if(format==='v1'){
   if(fields!=='environment,installation_id,request_id,secret,version' || value.version!==1
     || value.installation_id!==installation_id || value.environment!==environment || !uuid(value.request_id)
     || !currentSecret.test(value.secret))throw new RequestError('receipt_unavailable');
  }else if(format==='id-hex64'){
   if(fields!=='id,secret' || !uuid(value.id) || typeof value.secret!=='string' || !/^[a-f0-9]{64}$/.test(value.secret))
    throw new RequestError('receipt_unavailable');
   value={request_id:value.id,secret:value.secret};
  }else if(fields!=='request_id,secret,version' || value.version!==1 || !uuid(value.request_id)
    || typeof value.secret!=='string' || !/^[A-Za-z0-9_-]{43}$/.test(value.secret))throw new RequestError('receipt_unavailable');
  return Object.freeze({version:1,request_id:value.request_id,secret:value.secret});
 }
 function entries(storage){
  try{return readers.flatMap(reader=>{const raw=storage.getItem(reader.key);return raw===null?[]:[{key:reader.key,value:parse(raw,reader.format)}];});}
  catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
 }
 function readReceipt(storage){
  const saved=entries(storage);
  if(saved.some(item=>!equal(item.value,saved[0].value)))throw new RequestError('receipt_conflict');
  return saved[0]?.value || null;
 }
 function prepareReceipt(storage,policy,cryptoSource=globalThis.crypto){
  if(policy?.receipt_access?.version!==1 || !keyId.test(policy.receipt_access.key_id || ''))throw new RequestError('invalid_response');
  if(readReceipt(storage) || readRecovery(storage))throw new RequestError('checkout_in_progress');
  const bytes=cryptoSource.getRandomValues(new Uint8Array(32));
  const value={version:1,installation_id,environment,request_id:cryptoSource.randomUUID(),
   secret:'r1.'+policy.receipt_access.key_id+'.'+btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','')};
  const encoded=JSON.stringify(value);parse(encoded,'v1');
  try{storage.setItem(current,encoded);if(storage.getItem(current)!==encoded)throw Error();}
  catch{throw new RequestError('storage_unavailable');}
  return readReceipt(storage);
 }
 function clearReceipt(storage,expected){
  const saved=entries(storage);
  if(!expected || !uuid(expected.request_id) || !saved.length || saved.some(item=>!equal(item.value,expected)))throw new RequestError('receipt_conflict');
  try{for(const item of saved)storage.removeItem(item.key);if(readReceipt(storage)!==null)throw Error();}
  catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
 }
 function readRecovery(storage){
  try{const raw=storage.getItem(stageKey);return raw===null?null:parse(raw,'v1');}
  catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
 }
 function prepareRecovery(storage,reference,policy,source=globalThis.crypto){
  if(!uuid(reference) || policy?.receipt_access?.version!==1 || !keyId.test(policy.receipt_access.key_id || ''))throw new RequestError('invalid_request');
  const saved=readRecovery(storage),old=entries(storage);
  if((saved && saved.request_id!==reference) || old.some(item=>item.value.request_id!==reference))throw new RequestError('receipt_conflict');
  if(saved)return saved;
  const bytes=source.getRandomValues(new Uint8Array(32)),value={version:1,installation_id,environment,request_id:reference,
   secret:'r1.'+policy.receipt_access.key_id+'.'+btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','')};
  const encoded=JSON.stringify(value);parse(encoded,'v1');
  try{storage.setItem(stageKey,encoded);if(storage.getItem(stageKey)!==encoded)throw Error();}
  catch{throw new RequestError('storage_unavailable');}
  return readRecovery(storage);
 }
 function commitRecovery(storage,expected){
  const staged=readRecovery(storage),old=entries(storage);
  if(!staged || !expected || !equal(staged,expected) || old.some(item=>item.value.request_id!==staged.request_id))throw new RequestError('receipt_conflict');
  const encoded=JSON.stringify({version:1,installation_id,environment,request_id:staged.request_id,secret:staged.secret});
  try{
   storage.setItem(current,encoded);if(storage.getItem(current)!==encoded)throw Error();
   for(const item of old)if(item.key!==current)storage.removeItem(item.key);
   if(!equal(readReceipt(storage),staged))throw Error();
   storage.removeItem(stageKey);if(storage.getItem(stageKey)!==null)throw Error();
  }catch(error){if(error instanceof RequestError)throw error;throw new RequestError('storage_unavailable');}
  return staged;
 }
 return Object.freeze({readReceipt,prepareReceipt,clearReceipt,readRecovery,prepareRecovery,commitRecovery,storageKey:current});
}
