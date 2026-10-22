import {createStateController,publicDisplaySnapshot} from '../../../appointment-system/browser/product-state.mjs';
// This hint can preserve public labels; it never grants booking admission.
export function displayModeFromRoot(doc){return doc?.getElementById('root')?.dataset.publicMode==='on';}
const initial=publicDisplaySnapshot(typeof document!=='undefined'&&displayModeFromRoot(document));
export const productState=createStateController({serverSnapshot:()=>initial,initialDisplay:true});
