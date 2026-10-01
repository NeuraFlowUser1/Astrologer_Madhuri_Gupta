import {defineConfig} from 'vitest/config';
import {fileURLToPath} from 'node:url';
import react from '@vitejs/plugin-react';

// Explicit non-design scope. Unexecuted active files remain in the denominator.
// CSS, decorative motion, page artwork and static copy are outside this pass.
export default defineConfig({
  root:fileURLToPath(new URL('..',import.meta.url)),
  plugins:[react()],
  test:{
    include:['frontend/tests/verification/**/*.test.{mjs,jsx}'],
    environment:'node',
    clearMocks:true,
    restoreMocks:true,
    coverage:{
      provider:'istanbul',
      include:[
        'frontend/src/booking/{state,protocol,razorpay}.mjs',
        'frontend/src/booking/useBooking.jsx',
        'frontend/src/pages/Booking.jsx',
        'frontend/src/contact/{protocol.mjs,useEnquiry.jsx,ContactForm.jsx}',
        'frontend/src/site/{routes,page-metadata}.mjs',
        'backend/booking_engine/studio_assets/*.js',
        'workers/booking-recovery/{worker,monitor}.mjs',
      ],
      reporter:['text-summary','json','json-summary'],
      reportsDirectory:'tools/verification/artifacts/javascript',
    },
  },
});
