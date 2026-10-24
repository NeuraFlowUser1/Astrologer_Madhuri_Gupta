/** Focused phone/contact refinement proof; no provider or complete application gate. */
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({plugins:[react()],test:{
  environment:'jsdom',pool:'vmThreads',maxWorkers:2,
  include:[
    'tests/public-site/booking-frame.test.jsx',
    'tests/public-site/refinement-app.test.jsx',
    'tests/public-site/refinement-pages.test.jsx',
    'tests/public-site/restore-contact.test.jsx',
    'tests/public-site/contact-page-actions.test.jsx',
    'tests/public-site/vastu-metadata.test.mjs',
    'tests/verification/booking-flow.test.jsx',
  ],
  coverage:{provider:'istanbul',reporter:['text','json','json-summary'],
    reportsDirectory:'coverage/phone-contact',
    include:[
      'src/site/{SiteFrame,PhoneLink}.jsx',
      'src/site/{practice-contact,page-metadata}.mjs',
      'src/pages/{Booking,ContactPage}.jsx',
      'src/contact/ContactForm.jsx',
    ],exclude:[],thresholds:{perFile:true,statements:90,branches:90,functions:90,lines:90},
  },
}});
