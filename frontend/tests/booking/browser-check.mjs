/** Browser-only network interception: never imported by the website. No real payments or messages. */
async (page) => {
  const root = '/mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan';
  const policy = {
  "policy": {
    "project": "004-sarsa-jyotish-sansthan",
    "timezone": "Asia/Kolkata",
    "weekdays": [
      0,
      1,
      2,
      3,
      4,
      5
    ],
    "windows": [
      [
        "10:00",
        "12:00"
      ],
      [
        "15:00",
        "18:00"
      ]
    ],
    "slot_step_minutes": 30,
    "notice_minutes": 30,
    "advance_days": 10,
    "hold_minutes": 10,
    "receipt_after_hours": 24,
    "availability_authority": "website_staff_calendar",
    "services": [
      {
        "id": "kundli-matching",
        "name": "Kundli Matching",
        "amount_paise": 210000,
        "duration_minutes": 30,
        "currency": "INR",
        "meeting_platform": "Google Meet"
      },
      {
        "id": "kundli-prediction",
        "name": "Kundli Prediction",
        "amount_paise": 250000,
        "duration_minutes": 30,
        "currency": "INR",
        "meeting_platform": "Google Meet"
      },
      {
        "id": "vastu-consultation",
        "name": "Vastu Consultation",
        "amount_paise": 450000,
        "duration_minutes": 30,
        "currency": "INR",
        "meeting_platform": "Google Meet"
      },
      {
        "id": "numerology",
        "name": "Numerology",
        "amount_paise": 210000,
        "duration_minutes": 30,
        "currency": "INR",
        "meeting_platform": "Google Meet"
      }
    ]
  },
  "quote_version": "29824fcc90cabd9f8bd3245c787aa4b1694bd6270906fb65ba1eca3c2bd0fcd3"
};
  await page.unrouteAll({behavior:'wait'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  let saved=null,checkoutCalls=0,statusCalls=0,mode='normal',seen=[],scriptRequests=0;
  const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url());seen.push(url.pathname);
    if(url.pathname==='/api/booking-policy')return mode==='unavailable'?json(route,{code:'booking_unavailable'},503):json(route,policy);
    if(url.pathname==='/api/availability'){
      const service=policy.policy.services.find(s=>s.id===url.searchParams.get('service_id'));
      const date=url.searchParams.get('day');
      return json(route,{service:{...service,timezone:'Asia/Kolkata',quote_version:policy.quote_version},date,server_now:new Date().toISOString(),
        slots:[{starts_at:date+'T10:00:00+05:30',ends_at:date+'T10:30:00+05:30'},{starts_at:date+'T15:00:00+05:30',ends_at:date+'T15:30:00+05:30'}]});
    }
    if(url.pathname==='/api/checkout-context')return json(route,{ready:true});
    if(url.pathname==='/api/checkout'){
      checkoutCalls++;if(mode==='missing-payment')return json(route,{code:'payment_not_configured'},503);const body=request.postDataJSON();const service=policy.policy.services.find(s=>s.id===body.service_id);
      saved={request_id:body.request_id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',service_name:service.name,
        amount_paise:service.amount_paise,currency:'INR',timezone:'Asia/Kolkata',captured_paise:0,refunded_paise:0,
        starts_at:body.starts_at,ends_at:new Date(Date.parse(body.starts_at)+1800000).toISOString(),server_now:new Date().toISOString(),
        hold_expires_at:new Date(Date.now()+600000).toISOString(),next_actions:['resume_payment','check_status'],meeting_state:'not_created',meet_url:null,
        acknowledgement_state:'not_queued',meeting_email_state:'not_queued'};
      if(mode==='uncertain')return route.abort('failed');
      return json(route,{receipt:saved,checkout:{key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:service.amount_paise,currency:'INR'}});
    }
    if(url.pathname==='/api/checkout/status'){statusCalls++;return saved?json(route,saved):json(route,{code:'access_unavailable'},403)}
    if(url.pathname==='/api/checkout/verify-payment'){
      saved={...saved,appointment_state:'confirmed',payment_state:'captured',captured_paise:saved.amount_paise,next_actions:['check_status'],meeting_state:'preparing',acknowledgement_state:'pending',meeting_email_state:'pending'};
      return json(route,{receipt:saved,verification:'checked'});
    }
    return json(route,{code:'temporarily_unavailable'},503);
  });
  await page.route('https://checkout.razorpay.com/v1/checkout.js',route=>{scriptRequests++;return route.fulfill({contentType:'application/javascript',body:
    'window.Razorpay=function(options){window.__testPayment=options;this.open=()=>{window.__testOpened=(window.__testOpened||0)+1};this.close=()=>{}};'});});
  await page.goto('http://127.0.0.1:3014/#/booking');
  await page.evaluate(()=>sessionStorage.clear());await page.reload();
  const tomorrow=new Date(Date.now()+86400000).toISOString().slice(0,10);
  await page.locator('#appointment-date').fill(tomorrow);
  await page.getByLabel('10:00 am',{exact:false}).check();
  await page.locator('#full_name').fill('Synthetic Test');await page.locator('#email').fill('CaseSensitive@example.com');await page.locator('#phone').fill('9876543210');
  await page.locator('#notes').fill('Synthetic test question');
  await page.getByRole('checkbox').check();
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#review').scrollIntoViewIfNeeded();await page.waitForTimeout(2400);
  await page.screenshot({path:root+'/frontend/tests/booking/desktop-review.png'});
  await page.getByRole('button',{name:/Continue to payment ·/}).click();
  await page.waitForFunction(()=>window.__testOpened===1);
  const stored=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('sarsa:004:booking-receipt:v1')));
  if(Object.keys(stored).sort().join(',')!=='request_id,secret,version')throw Error('Unexpected stored data');
  if(checkoutCalls!==1)throw Error('Multiple reservations');
  await page.evaluate(()=>window.__testPayment.handler({razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'a'.repeat(64)}));
  await page.getByRole('heading',{name:'Your appointment is confirmed.'}).waitFor();
  if(await page.getByText('Delivered',{exact:true}).count())throw Error('False delivered claim');
  await page.setViewportSize({width:390,height:844});await page.locator('#receipt').scrollIntoViewIfNeeded();await page.waitForTimeout(1000);
  await page.screenshot({path:root+'/frontend/tests/booking/phone-confirmed.png'});
  await page.reload();await page.getByRole('heading',{name:'Your appointment is confirmed.'}).waitFor();
  if(checkoutCalls!==1)throw Error('Refresh repeated checkout');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw Error('Phone overflow');
  // A lost checkout response must recover the same stored receipt after refresh.
  mode='uncertain';saved=null;await page.evaluate(()=>sessionStorage.clear());await page.reload();
  await page.locator('#appointment-date').fill(tomorrow);await page.getByLabel('10:00 am',{exact:false}).check();
  await page.locator('#full_name').fill('Synthetic Test');await page.locator('#email').fill('case@example.com');await page.locator('#phone').fill('9876543210');await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:/Continue to payment ·/}).click();
  await page.getByRole('button',{name:'Retry the same saved request'}).waitFor();
  const before=checkoutCalls;await page.reload();await page.getByRole('heading',{name:'Your time is reserved.'}).waitFor();
  if(checkoutCalls!==before)throw Error('Lost response created another order');
  mode='missing-payment';saved=null;await page.evaluate(()=>sessionStorage.clear());await page.reload();
  await page.locator('#appointment-date').fill(tomorrow);await page.getByLabel('10:00 am',{exact:false}).check();
  await page.locator('#full_name').fill('Retained Person');await page.locator('#email').fill('retained@example.com');await page.locator('#phone').fill('9876543210');await page.getByRole('checkbox').check();
  const scriptsBefore=scriptRequests;
  await page.getByRole('button',{name:/Continue to payment ·/}).click();
  await page.getByText('We could not start payment.',{exact:false}).waitFor();
  await page.waitForTimeout(300);
  if(scriptRequests!==scriptsBefore)throw Error('Missing configuration loaded payment script');
  if(await page.evaluate(()=>sessionStorage.getItem('sarsa:004:booking-receipt:v1')))throw Error('Proven rejection kept stale receipt');
  if(await page.locator('#full_name').inputValue()!=='Retained Person')throw Error('Lost entered details');
  if(!(await page.getByLabel('10:00 am',{exact:false}).isChecked()))throw Error('Lost still-available selected time');
  mode='unavailable';saved=null;await page.evaluate(()=>sessionStorage.clear());await page.reload();
  await page.getByRole('alert').waitFor();
  if(await page.locator('.slot-option').count())throw Error('Fabricated fallback times');
  if(!(await page.getByRole('button',{name:/Continue to payment/}).isDisabled()))throw Error('Unavailable payment enabled');
  await page.setViewportSize({width:320,height:800});await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(3900);
  await page.screenshot({path:root+'/frontend/tests/booking/phone-320-unavailable.png'});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('320px overflow');
  if(errors.length)throw Error('Browser errors: '+errors.join(';'));
  return {passed:true,checkoutCalls,statusCalls,privateStorageFields:Object.keys(stored),unexpectedApi:seen.filter(p=>!['/api/booking-policy','/api/availability','/api/checkout-context','/api/checkout','/api/checkout/status','/api/checkout/verify-payment'].includes(p))};
}
