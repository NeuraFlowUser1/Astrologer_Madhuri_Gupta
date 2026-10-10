/** Decorative directory artwork uses the same four motifs as the existing site. */
export default function ServiceArtwork({id}){
  const art={
    'kundli-matching':<><circle cx="134" cy="88" r="62"/><circle cx="218" cy="88" r="62"/><path d="M134 38l50 50-50 50-50-50ZM218 38l50 50-50 50-50-50Z"/><circle cx="176" cy="88" r="13" className="art-accent"/></>,
    'kundli-prediction':<><path d="M176 14l74 74-74 74-74-74ZM102 14h148v148H102ZM102 14l148 148M250 14 102 162M176 14v148M102 88h148"/><circle cx="176" cy="88" r="23" className="art-accent"/><circle cx="176" cy="88" r="8"/></>,
    'vastu-consultation':<><path d="M103 34h146v112H103ZM103 34l48 27h146l-48-27M249 34l48 27v112l-48-27M103 146l48 27h146M151 61v112M194 61v112M151 119h146"/><path className="art-accent" d="M176 6v26m-7-7 7 7 7-7"/></>,
    numerology:<><rect x="83" y="30" width="60" height="112" rx="14" transform="rotate(-8 113 86)"/><rect className="art-accent" x="146" y="20" width="60" height="112" rx="14"/><rect x="209" y="39" width="60" height="112" rx="14" transform="rotate(8 239 95)"/><text x="113" y="103">3</text><text x="176" y="93">6</text><text x="239" y="112">9</text></>,
  }[id];
  return art?<div className="directory-art"><svg viewBox="0 0 352 176" aria-hidden="true">{art}</svg></div>:null;
}
