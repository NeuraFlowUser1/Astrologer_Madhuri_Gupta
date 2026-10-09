/** Build the displayed pages and exact asset boundary; no provider access. */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pages} from '../src/site/page-metadata.mjs';
import project from '../../appointment-settings/project.json' with {type:'json'};
import publicAssets from '../../appointment-settings/public-assets.json' with {type:'json'};
import {generateModes} from '../../appointment-system/tools/build/page-modes.mjs';
import {writeSurfaceManifest} from '../../appointment-system/tools/build/surfaces.mjs';
const dist=resolve(import.meta.dirname,'../dist');
const bookingPaths=['/booking','/booking/receipt','/booking-help','/booking-policy'];
const manifest=writeSurfaceManifest({dist,publicDirectory:resolve(import.meta.dirname,'../public'),project,
 publicPaths:Object.keys(pages).filter(path=>!bookingPaths.includes(path)),bookingPaths,
 backendPaths:['/studio','/enquiries-studio'],publicAssets});
// A repeated invocation may read the already generated OFF shell. Remove its
// marker before rendering; each route must contain exactly its own mode.
const shell=readFileSync(resolve(dist,'index.html'),'utf8').replace(/<meta name="booking-display-mode" content="(?:on|off)">/g,'');
generateModes({dist,shell,pages,project,manifest,brand:project.label,offDescriptions:{
 '/':'Explore astrology, Numerology and Vastu guidance with Madhuri Gupta at Sarsa Jyotish Sansthan. Contact the practice with your questions.',
 '/services':'Explore Kundli Prediction, Kundli Matching, Vastu and Numerology guidance. Contact the practice with your questions.',
 '/contact':'Send Sarsa Jyotish Sansthan a question or contact the practice for help.'}});
console.log('Generated public pages and classified asset boundary from the contained release.');
