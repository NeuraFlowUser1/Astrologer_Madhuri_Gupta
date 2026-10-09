import {test,expect,vi} from 'vitest';
const mocks=vi.hoisted(()=>({refresh:vi.fn(async()=>{}),start:vi.fn(),render:vi.fn(),recovery:vi.fn(),conditional:vi.fn()}));
vi.mock('react-dom/client',()=>({default:{createRoot:()=>({render:mocks.render})}}));
vi.mock('../../src/App.jsx',()=>({default:()=>null}));
vi.mock('../../src/site/product-state.mjs',()=>({productState:{refresh:mocks.refresh,start:mocks.start}}));
vi.mock('../../../appointment-system/browser/conditional-work.mjs',()=>({startWhenBookingOn:mocks.conditional}));
vi.mock('../../src/booking/browser.mjs',()=>({bookingBrowser:{recovery:{start:mocks.recovery}}}));
test('startup verifies display first and registers booking-only work before rendering',async()=>{
 document.body.innerHTML='<div id="root"></div>';await import('../../src/main.jsx');for(let i=0;i<8;i++)await Promise.resolve();expect(mocks.refresh).toHaveBeenCalledWith({force:true});expect(mocks.start).toHaveBeenCalledOnce();expect(mocks.render).toHaveBeenCalledOnce();expect(mocks.refresh.mock.invocationCallOrder[0]).toBeLessThan(mocks.render.mock.invocationCallOrder[0]);const work=await mocks.conditional.mock.calls[0][0]();work();expect(mocks.recovery).toHaveBeenCalledOnce();
});
