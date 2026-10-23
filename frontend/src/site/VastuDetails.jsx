import {useState} from 'react';
import {vastuConcepts} from './vastu-content.mjs';
import heroSmall from './media/vastu/vastu-home-cutaway-480.webp';
import heroMedium from './media/vastu/vastu-home-cutaway-800.webp';
import heroLarge from './media/vastu/vastu-home-cutaway-1200.webp';
import './vastu.css';

export function VastuHero(){return (<figure className="service-art vastu-hero-art">
        <div className="hero-material" data-layer aria-hidden="true"/>
        <img id="hero-image" data-layer src={heroLarge} srcSet={`${heroSmall} 480w, ${heroMedium} 800w, ${heroLarge} 1200w`} sizes="(max-width: 700px) calc(100vw - 48px), (max-width: 850px) 600px, 50vw" fetchPriority="high" decoding="async" width="1200" height="900" alt="An illustrative home model showing an entrance, rooms and windows beside a compass."/>
        <figcaption data-layer>A home, considered as a whole.</figcaption>
      </figure>);}

export function VastuTopics(){return (<div className="detail-topics">
        <article data-layer>
          <div className="topic-illustration" aria-hidden="true"><svg viewBox="0 0 120 86"><path className="diagram-wash" d="M14 12h92v62H14z"/><path d="M14 12h92v62H14zM61 12v32h45M14 44h27m20 0v30M41 44h20M14 60h16M30 60v14"/><path className="diagram-gold" d="M48 74v-9m0 0a9 9 0 0 1 9 9M91 19v17m-5-6 5 6 5-6"/></svg></div>
          <h3>Your layout</h3><p>The rooms, entrance and fixed features you want to discuss.</p>
        </article>
        <article data-layer>
          <div className="topic-illustration" aria-hidden="true"><svg viewBox="0 0 120 86"><path className="diagram-wash" d="M21 16h78v56H21z"/><path d="M21 16h78v56H21zM60 16v56M21 44h78"/><circle className="diagram-gold" cx="60" cy="44" r="15"/><path className="diagram-gold" d="M60 22v-7m0 58v-7M38 44h-7m58 0h-7"/></svg></div>
          <h3>Your daily life</h3><p>Where your family sleeps, cooks, prays and spends time together.</p>
        </article>
        <article data-layer>
          <div className="topic-illustration" aria-hidden="true"><svg viewBox="0 0 120 86"><path className="diagram-wash" d="M20 15h80v57H20z"/><path d="M20 15h80v57H20zM20 43h28m25 0h27M60 15v17m0 23v17"/><path className="diagram-gold" d="M45 43h30m-8-8 8 8-8 8"/><circle cx="44" cy="43" r="3"/></svg></div>
          <h3>Your priorities</h3><p>What concerns you, what is fixed and what you are considering changing.</p>
        </article>
      </div>);}

export function VastuPrinciples(){
 const [selected,setSelected]=useState('mandala'),concept=vastuConcepts[selected];
 return (<section className="vastu-principles" data-service-scene="principles" data-principle={selected} id="vastu-principles" aria-labelledby="principles-title">
      <div className="principles-intro">
        <p className="eyebrow">A TRADITIONAL FRAMEWORK</p>
        <h2 id="principles-title">The principles behind the plan.</h2>
        <p>The layout, its centre and the qualities of each space are considered together.</p>
      </div>
      <div className="principles-grid">
        <figure className="principles-visual">
          <svg viewBox="0 0 520 470" role="img" aria-labelledby="principles-diagram-title principles-diagram-description">
            <title id="principles-diagram-title">{concept.name}</title>
            <desc id="principles-diagram-description">{concept.description}</desc>
            <defs><filter id="principles-paper-shadow" x="-25%" y="-25%" width="150%" height="160%"><feDropShadow dx="0" dy="12" stdDeviation="14" floodColor="#10291f" floodOpacity=".25"/></filter></defs>
            <g data-principles-stage="paper" aria-hidden="true"><rect className="principles-paper-shadow" x="72" y="47" width="382" height="386" rx="19"/><rect className="principles-paper" x="66" y="38" width="388" height="394" rx="19"/></g>
            <g data-principles-stage="grid" aria-hidden="true">
              <g className="principles-grid-lines"><rect x="98" y="74" width="324" height="324"/><g><line data-grid-line="column" x1="134" y1="74" x2="134" y2="398"/><line data-grid-line="column" x1="170" y1="74" x2="170" y2="398"/><line data-grid-line="column" x1="206" y1="74" x2="206" y2="398"/><line data-grid-line="column" x1="242" y1="74" x2="242" y2="398"/><line data-grid-line="column" x1="278" y1="74" x2="278" y2="398"/><line data-grid-line="column" x1="314" y1="74" x2="314" y2="398"/><line data-grid-line="column" x1="350" y1="74" x2="350" y2="398"/><line data-grid-line="column" x1="386" y1="74" x2="386" y2="398"/><line data-grid-line="row" x1="98" y1="110" x2="422" y2="110"/><line data-grid-line="row" x1="98" y1="146" x2="422" y2="146"/><line data-grid-line="row" x1="98" y1="182" x2="422" y2="182"/><line data-grid-line="row" x1="98" y1="218" x2="422" y2="218"/><line data-grid-line="row" x1="98" y1="254" x2="422" y2="254"/><line data-grid-line="row" x1="98" y1="290" x2="422" y2="290"/><line data-grid-line="row" x1="98" y1="326" x2="422" y2="326"/><line data-grid-line="row" x1="98" y1="362" x2="422" y2="362"/></g></g>
              <g className="principles-cardinals"><text x="260" y="59">N</text><text x="260" y="420">S</text><text x="82" y="243">W</text><text x="438" y="243">E</text></g>
            </g>
            <g data-principles-stage="plan" aria-hidden="true">
              <g className="principles-home-plan"><path d="M98 74h324v324H286m-38 0H98V74M98 182h108V74M314 74v108h108M98 290h108v108M314 398V290h108"/><path className="principles-plan-door" d="M248 398v-36a36 36 0 0 1 36 36"/><rect className="principles-room-wash" x="103" y="79" width="98" height="98"/><rect className="principles-room-wash" x="319" y="295" width="98" height="98"/></g>
            </g>
            <g data-principles-stage="emphasis" aria-hidden="true">
              <g className="principles-centre"><rect x="206" y="182" width="108" height="108"/><path d="M206 218h108M206 254h108M242 182v108M278 182v108"/><circle cx="260" cy="236" r="7"/></g>
              <g className="principles-elements">
                <path className="element-connection" d="M260 117 374 218 329 337 191 337 146 218Z"/>
                <g className="principles-element element-space"><circle cx="260" cy="117" r="21"/><circle cx="260" cy="117" r="11"/><circle cx="260" cy="117" r="3"/><text x="260" y="163">Space</text></g>
                <g className="principles-element element-fire"><path d="M373 190c4 15-12 16-12 29 0 18 27 20 29 2 2-12-7-14-7-21-3 6-7 9-8 12 1-9 4-14-2-22Z"/><text x="374" y="263">Fire</text></g>
                <g className="principles-element element-water"><path d="M329 311c-3 11-17 21-17 31a17 17 0 0 0 34 0c0-10-14-20-17-31Z"/><path d="M320 342a9 9 0 0 0 9 9"/><text x="329" y="382">Water</text></g>
                <g className="principles-element element-earth"><path d="M169 329 191 316l22 13-22 13ZM169 340l22 13 22-13M169 351l22 13 22-13"/><text x="191" y="397">Earth</text></g>
                <g className="principles-element element-air"><path d="M122 209h30c17 0 15-18 4-18-5 0-8 3-8 7M122 220h39c17 0 16 19 4 19-5 0-9-3-9-7M129 232h14"/><text x="146" y="271">Air</text></g>
              </g>
            </g>
          </svg>
          <figcaption id="principles-diagram-caption">{concept.caption}</figcaption>
        </figure>
        <div className="principles-copy">
          <div className="principles-choices" aria-label="Explore traditional Vastu principles">
            {Object.entries(vastuConcepts).map(([key,item])=><button key={key} type="button" aria-pressed={selected===key} onClick={()=>setSelected(key)}>{item.label}</button>)}
          </div>
          <div className="principles-heading-stack"><h3>{concept.name}</h3>{Object.values(vastuConcepts).map(item=><h3 key={item.name} className="principles-measure" aria-hidden="true">{item.name}</h3>)}</div>
          <p className="principles-gloss">{concept.gloss}</p>
          <div className="principles-body-stack" aria-live="polite" aria-atomic="true"><p>{concept.body}</p>{Object.values(vastuConcepts).map(item=><p key={item.name} className="principles-measure" aria-hidden="true">{item.body}</p>)}</div>
        </div>
      </div>
    </section>);
}
