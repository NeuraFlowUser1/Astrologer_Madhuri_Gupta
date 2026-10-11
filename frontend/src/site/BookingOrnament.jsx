import {useLayoutEffect,useRef} from 'react';
import {mountBookingOrnament} from './booking-ornament.mjs';
import './page-rhythm.css';

export default function BookingOrnament(){
 const root=useRef(null);
 useLayoutEffect(()=>mountBookingOrnament(root.current),[]);
 return <div className="booking-ornament" ref={root} aria-hidden="true">
  <svg viewBox="0 0 240 240" fill="none">
   <g data-art="orbit"><circle cx="120" cy="120" r="106" pathLength="1"/><circle cx="120" cy="120" r="92" pathLength="1" className="ornament-dashed"/></g>
   <g data-art="kundli"><path pathLength="1" d="M120 48 192 120 120 192 48 120ZM48 48h144v144H48ZM48 48l144 144M192 48 48 192"/><circle cx="120" cy="120" r="5"/></g>
   <g className="booking-orbit"><path d="M120 14a106 106 0 0 1 106 106" className="ornament-gold"/>
    <g data-art="points"><circle cx="120" cy="14" r="4"/><circle cx="226" cy="120" r="4"/><circle cx="120" cy="226" r="4"/><path d="m45 39 2 4 4 2-4 2-2 4-2-4-4-2 4-2Z"/></g>
   </g>
  </svg>
 </div>;
}
