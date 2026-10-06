/** Loopback parent bridge only. No provider requests, mail or personal data. */
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
import {createEnquiryBrowser} from '../browser/enquiry/index.mjs';
const lines=createInterface({input:process.stdin,crlfDelay:Infinity}),pending=new Map();let sequence=0;
lines.on('line',line=>{const value=JSON.parse(line),resolve=pending.get(value.id);pending.delete(value.id);resolve(value);});
const bridge=(path,options={})=>new Promise(resolve=>{const id=++sequence;pending.set(id,resolve);process.stdout.write(JSON.stringify({id,path,...options})+'\n');});
const settings=(await bridge('test:settings')).body,values=new Map();
const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
const browser=createEnquiryBrowser({...settings,version:1,channels:{contact:{legacy_receipts:[]},prashna:{legacy_receipts:[]}}},
 {storage:()=>storage,fetcher:async(path,options)=>{const response=await bridge(path,{...(options.body?{body:JSON.parse(options.body)}:{}),headers:options.headers});
  return new Response(JSON.stringify(response.body),{status:response.status,headers:{'content-type':'application/json',...response.headers}});}});
const until=async fn=>{const started=Date.now();while(!fn()){if(Date.now()-started>15000)throw Error('Timed out waiting for enquiry state');await new Promise(resolve=>setTimeout(resolve,10));}};
for(const kind of ['contact','prashna']){
 let controller=browser.controller(kind);controller.start();
 await controller.submit({name:'Synthetic Customer',email:'customer@example.com',phone:kind==='prashna'?'+919876543210':'',
  subject:'Synthetic enquiry',message:'A synthetic question for local proof.',kind,source:kind==='contact'?'home':'prashna',
  ...(kind==='prashna'?{location:'Synthetic city',service_interest:'prashna'}:{dob:'2000-01-01'})});
 assert.equal(controller.getSnapshot().receipt?.state,'awaiting_verification',controller.getSnapshot().error);
 const id=controller.getSnapshot().receipt.request_id;controller.stop();controller=browser.controller(kind);controller.start();
 await until(()=>!!controller.getSnapshot().receipt);assert.equal(controller.getSnapshot().receipt.request_id,id);
 const code=(await bridge('test:code',{request_id:id})).body.value;await controller.verify(code);
 assert.equal(controller.getSnapshot().receipt.state,'received',controller.getSnapshot().error);
 await controller.check();assert.equal(controller.getSnapshot().receipt.state,'received');controller.stop();
}
await bridge('test:finished');lines.close();
