import {useState} from 'react';
import media from './service-media.json';
import ServiceArtwork from './ServiceArtwork.jsx';
import './service-media.css';

// Vite owns these image URLs and records their general-public bundle ownership.
const imageUrls=import.meta.glob('./media/services/*.webp',{eager:true,query:'?url',import:'default'});

/** Image paths and crop information only; the product catalogue owns service facts. */
export function imageSource(serviceId,index=0,detail=false){
  const image=media[serviceId]?.images[index];
  if(!image)return null;
  const renditions=image.renditions.filter(r=>detail?r.width>=800:r.width<=960).map(r=>({...r,src:imageUrls[r.src]}));
  return {...image,src:renditions.at(-1).src,srcSet:renditions.map(r=>`${r.src} ${r.width}w`).join(', ')};
}

export default function ServiceMedia({serviceId,index=0,detail=false,className='',onFailure,hidden=false}){
  const [failed,setFailed]=useState(false),image=imageSource(serviceId,index,detail);
  if(!image)return null;
  return <div className={'service-media '+className} aria-hidden={hidden||undefined}>
    {failed?<div className="service-media-fallback" role="img" aria-label={image.alt}>
      <ServiceArtwork id={serviceId}/><span>Service illustration</span>
    </div>:<img src={image.src} srcSet={image.srcSet}
      sizes={detail?'(max-width: 700px) calc(100vw - 48px), (max-width: 1240px) 55vw, 640px':'(max-width: 650px) calc(100vw - 96px), (max-width: 1240px) 42vw, 510px'}
      width={image.width} height={image.height} alt={hidden?'':image.alt}
      style={{objectPosition:image.focal}} loading="lazy" decoding="async"
      onError={()=>{setFailed(true);onFailure?.(index);}}/>}
  </div>;
}
