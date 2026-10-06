const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function facts(env) {
  const value={installation_id:env.BOOKING_INSTALLATION_ID,project:env.BOOKING_PROJECT_ID,
    environment:env.BOOKING_ENVIRONMENT,origin:env.BOOKING_PUBLIC_ORIGIN};
  if (!UUID.test(value.installation_id || '') || value.installation_id === '00000000-0000-0000-0000-000000000000'
      || !/^[a-z0-9][a-z0-9-]{0,74}$/.test(value.project || '')
      || !['production','development','test'].includes(value.environment)
      || typeof value.origin !== 'string' || !/^[\x21-\x7e]+$/.test(value.origin)) throw Error('state_configuration');
  let url;try{url=new URL(value.origin);}catch{throw Error('state_configuration');}
  if (url.origin!==value.origin || url.username || url.password || url.pathname!=='/' || url.search || url.hash
      || (url.protocol!=='https:' && !(value.environment!=='production' && url.protocol==='http:' && ['localhost','127.0.0.1'].includes(url.hostname))))
    throw Error('state_configuration');
  return value;
}
