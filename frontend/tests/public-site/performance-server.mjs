/** Loopback-only gzip transport for the unchanged built-source display proof. */
import {createServer} from 'node:http';
import {gzipSync} from 'node:zlib';
export async function compressedProof(proof){
 const server=createServer(async(request,response)=>{
  if(!['GET','HEAD'].includes(request.method)){response.writeHead(405);return response.end();}
  try{const upstream=await fetch(new URL(request.url,proof.origin),{method:request.method});const bytes=Buffer.from(await upstream.arrayBuffer()),headers=Object.fromEntries(upstream.headers);
   delete headers.connection;delete headers['transfer-encoding'];delete headers['content-length'];
   const compress=/^(text\/|application\/(json|javascript|xml))/.test(headers['content-type']||'');const body=compress?gzipSync(bytes):bytes;
   if(compress)headers['content-encoding']='gzip';headers['content-length']=String(body.byteLength);response.writeHead(upstream.status,headers);response.end(request.method==='HEAD'?undefined:body);
  }catch{response.writeHead(503);response.end('Local performance proof unavailable');}
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return {...proof,origin:'http://127.0.0.1:'+server.address().port,close:async()=>{await new Promise(resolve=>server.close(resolve));await proof.close();}};
}
