import {test,expect,vi} from 'vitest';
const mocks=vi.hoisted(()=>({refresh:vi.fn(async()=>{}),start:vi.fn(),render:vi.fn(),hydrate:vi.fn(),recovery:vi.fn(),conditional:vi.fn()}));
vi.mock('react-dom/client',()=>({createRoot:()=>({render:mocks.render}),hydrateRoot:mocks.hydrate}));
vi.mock('../../src/App.jsx',()=>({default:()=>null}));
vi.mock('../../src/site/product-state.mjs',()=>({productState:{refresh:mocks.refresh,start:mocks.start}}));
vi.mock('../../../appointment-system/browser/conditional-work.mjs',()=>({startWhenBookingOn:mocks.conditional}));
vi.mock('../../src/booking/browser.mjs',()=>({bookingBrowser:{recovery:{start:mocks.recovery}}}));
test('startup retains generated public content, owns one lifetime and still requires a live check',async()=>{
 window.history.replaceState({},'','/about');document.body.innerHTML='<div id="root" data-public-path="/about" data-public-mode="on" data-public-render="sarsa-public-v1"><h1>Existing actual content</h1></div>';
 await import('../../src/main.jsx');for(let i=0;i<8;i++)await Promise.resolve();
 expect(mocks.hydrate).toHaveBeenCalledOnce();expect(mocks.render).not.toHaveBeenCalled();expect(mocks.hydrate.mock.calls[0][2].identifierPrefix).toBe('sarsa-public-');
 expect(mocks.refresh).toHaveBeenCalledWith({force:true});expect(mocks.start).toHaveBeenCalledOnce();expect(mocks.start).toHaveBeenCalledWith(window,document,{profile:'public',refreshOnStart:false});
 expect(mocks.hydrate.mock.invocationCallOrder[0]).toBeLessThan(mocks.refresh.mock.invocationCallOrder[0]);expect(document.querySelector('h1').textContent).toBe('Existing actual content');
 const work=await mocks.conditional.mock.calls[0][0]();work();expect(mocks.recovery).toHaveBeenCalledOnce();
 vi.resetModules();mocks.render.mockClear();mocks.hydrate.mockClear();document.getElementById('root').removeAttribute('data-public-render');
 await import('../../src/main.jsx');expect(mocks.render).toHaveBeenCalledOnce();expect(mocks.hydrate).not.toHaveBeenCalled();
});
