import {useId} from 'react';

/** Permanent question/chart/clock composition; each instance owns its SVG IDs. */
export default function PrashnaArtwork({compact=false}){
 const id=useId().replace(/[^a-zA-Z0-9_-]/g,''),paper=`prashna-paper-${id}`,brass=`prashna-brass-${id}`,ground=`prashna-ground-${id}`,shadow=`prashna-shadow-${id}`;
 return <svg viewBox="0 0 320 240" aria-hidden="true" focusable="false">
  <defs>
   <linearGradient id={paper} x2=".8" y2="1"><stop stopColor="#fffdf8"/><stop offset="1" stopColor="#e6ddc8"/></linearGradient>
   <linearGradient id={brass} x2="1" y2="1"><stop stopColor="#d2b577"/><stop offset=".45" stopColor="#b38e50"/><stop offset="1" stopColor="#806336"/></linearGradient>
   <radialGradient id={ground}><stop stopColor="#f6f0e2"/><stop offset="1" stopColor="#dedfce"/></radialGradient>
   <filter id={shadow} x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="7" stdDeviation="5" floodColor="#26483d" floodOpacity=".17"/></filter>
  </defs>
  {!compact&&<g data-art-part="foundation"><rect width="320" height="240" fill={`url(#${ground})`}/><path d="M260 0H320V240H282C276 169 266 104 260 0Z" fill="#26483d" opacity=".9"/><path d="M287 0C275 82 302 135 292 240" fill="none" stroke="#62785f" strokeWidth="1.5" opacity=".5"/></g>}
  <g filter={compact?undefined:`url(#${shadow})`}>
   <g data-art-part="leaf-left"><path d="M56 26 148 30V220L60 214Z" fill={`url(#${paper})`} stroke="#d5cbb5" strokeWidth=".8"/>{!compact&&<path d="M65 37 138 40V206L69 201Z" fill="none" stroke="#a6814d" strokeWidth=".8" opacity=".5"/>}</g>
   <g data-art-part="leaf-right"><path d="M148 30 238 26 235 215 148 220Z" fill={`url(#${paper})`} stroke="#d5cbb5" strokeWidth=".8"/>{!compact&&<path d="M157 40 228 37 226 202 157 206Z" fill="none" stroke="#a6814d" strokeWidth=".8" opacity=".5"/>}</g>
  </g>
  <g data-art-part="chart" fill="none" stroke="#526456" strokeWidth={compact?3:1.4}><path d="M93 65H203V175H93Z M148 65 203 120 148 175 93 120Z M93 65 203 175 M203 65 93 175"/>{!compact&&<circle cx="148" cy="120" r="3.2" fill="#a6814d" stroke="none"/>}</g>
  {!compact&&<g data-art-part="note" filter={`url(#${shadow})`}><g data-ambient-part="note"><path d="M40 153 135 158 130 211 43 207Z" fill="#fffdf8" stroke="#c9bda5" strokeWidth=".8"/><path d="M43 207 62 190 40 153" fill="#e7dfca"/><text x="70" y="179" fontFamily="Georgia,serif" fontSize="14" fontStyle="italic" fill="#26483d">Sawaal</text><path d="M69 190 116 193 M69 198 104 200" fill="none" stroke="#a6814d" strokeWidth=".8"/></g></g>}
  <g data-art-part="clock" filter={compact?undefined:`url(#${shadow})`}><g data-ambient-part={compact?undefined:'clock'}><circle cx="246" cy="74" r="30" fill={`url(#${brass})`} stroke="#806336" strokeWidth="1"/><circle cx="246" cy="74" r="25" fill="#f7f0df" stroke="#a6814d" strokeWidth=".8"/><path d="M246 52v4 M246 92v4 M224 74h4 M264 74h4" stroke="#806336" strokeWidth="1.3" fill="none"/><path d="M246 60v14l10 8" fill="none" stroke="#26483d" strokeWidth={compact?3:1.8} strokeLinecap="round"/><circle cx="246" cy="74" r="2" fill="#26483d"/></g></g>
 </svg>;
}
