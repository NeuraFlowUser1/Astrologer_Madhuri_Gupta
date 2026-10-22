/** The 960×1440 portrait keeps its original object-fit crop inside a stable scene.
 * Only the existing About layout owner measures geometry; frames change transforms. */
export function portraitTransform({width,height,mobile,progress}){
 const p=Math.max(0,Math.min(1,progress));
 const boxWidth=width*(mobile?1-.14*p:.66-.20*p),boxHeight=height*(mobile?1-.56*p:1);
 const left=width*(mobile?.5:.62-.37*p)-boxWidth/2,top=height*(mobile?.05*p:0);
 const scale=Math.max(boxWidth/width,boxHeight/(width*1.5));
 const x=left+(boxWidth-width*scale)*.5,y=top+(boxHeight-width*1.5*scale)*(mobile?.38:.35);
 return `translate(${x}px,${y}px) scale(${scale})`;
}
