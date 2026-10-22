/** Build-only entry: actual public tree, with no browser startup or live reads. */
import React from 'react';
import {renderToString} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import {AppShell} from './App.jsx';
import {BookingStateProvider} from './site/BookingProduct.jsx';
import {createStateController,publicDisplaySnapshot} from '../../appointment-system/browser/product-state.mjs';
import {publicPaths} from './site/page-metadata.mjs';
export function renderPublicPage(path,mode){
 if(!publicPaths.includes(path)||!['on','off'].includes(mode))throw Error('Only reviewed public routes and display modes can be generated.');
 const snapshot=publicDisplaySnapshot(mode==='on');
 const controller=createStateController({serverSnapshot:()=>snapshot});
 const body=renderToString(<React.StrictMode><BookingStateProvider controller={controller}><MemoryRouter initialEntries={[path]}><AppShell/></MemoryRouter></BookingStateProvider></React.StrictMode>,{identifierPrefix:'sarsa-public-'});
 if(body.includes('Loading the page…')||body.includes('BAILOUT_TO_CLIENT_SIDE_RENDERING'))throw Error('A public page did not render its actual content: '+path);
 return body;
}
