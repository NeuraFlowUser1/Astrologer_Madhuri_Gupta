import {PublicPage,copy,Action,ServiceCards} from '../site/PublicSections.jsx';
export default function Services(){return <PublicPage className="sarsa-services">
 <section className="section compact-opening"><div className="wrap"><h1 tabIndex={-1}>{copy.directory.title}</h1><p className="hindi" lang="hi">{copy.directory.hindi}</p><p>{copy.directory.body}</p><ServiceCards/></div></section>
 <section className="section sage"><div className="wrap"><h2>{copy.directory.matching_title}</h2><div className="choice-list">{copy.services.map(s=><p key={s.id}><strong>{s.name}</strong><span>{s.description}</span></p>)}</div></div></section>
 <section className="section knowledge"><div className="wrap two-column"><div><h2>{copy.directory.knowledge_title}</h2><dl>{copy.directory.glossary.map(([title,body])=><div key={title}><dt>{title}</dt><dd>{body}</dd></div>)}</dl></div><img src="/media/sarsa-public/kundli-prediction-illustration.svg" width="640" height="320" alt="" loading="lazy"/></div></section>
 <section className="section ending sage"><div className="wrap"><h2>{copy.directory.preparation_title}</h2><p>{copy.directory.preparation_body}</p><Action to="/contact">Ask a question</Action></div></section>
 </PublicPage>;}
