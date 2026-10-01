import {test,vi} from 'vitest';

// Run the existing assert-based tests unchanged under the coverage collector.
// They retain their native `node --test` entry point as well.
vi.mock('node:test',()=>({default:(name,body)=>test(name,context=>body({
  ...context,
  mock:{method:(target,key,implementation)=>vi.spyOn(target,key).mockImplementation(implementation)},
}))}));
await import('../booking/state.test.mjs');
await import('../booking/protocol.test.mjs');
await import('../contact/protocol.test.mjs');
await import('../routes.test.mjs');
await import('../../../workers/booking-recovery/worker.test.mjs');
