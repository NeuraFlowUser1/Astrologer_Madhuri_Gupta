export const testimonialServices = Object.freeze([
  {id:'kundli-prediction',label:'Kundli Prediction',icon:'chart'},
  {id:'kundli-matching',label:'Kundli Matching',icon:'matching'},
  {id:'vastu-consultation',label:'Vastu Consultation',icon:'vastu'},
  {id:'numerology',label:'Numerology',icon:'number'},
]);
export const testimonialThemes = Object.freeze([
  {id:'heard',label:'She listened',category:'numerology'},
  {id:'simple',label:'She explained clearly',category:'vastu-consultation'},
  {id:'calm',label:'Time to think',category:'kundli-matching'},
]);

/** Static editorial records: fail visibly during development if the source is malformed. */
export function buildTestimonialIndex(source){
  const ids=new Set();
  for(const story of source){
    if(!story || typeof story.id!=='string' || !story.id || ids.has(story.id) ||
      !testimonialServices.some(service=>service.id===story.category) ||
      !['name','city','initials','service','quote','context','lang'].every(key=>typeof story[key]==='string'&&story[key].trim()) ||
      !Array.isArray(story.paragraphs) || !story.paragraphs.length || story.paragraphs.some(text=>typeof text!=='string'||!text.trim())){
      throw new Error('Invalid testimonial content: check unique IDs, service, attribution and complete story text.');
    }
    ids.add(story.id);
  }
  const groups=testimonialServices.map(service=>source.filter(story=>story.category===service.id));
  const stories=Array.from({length:Math.max(0,...groups.map(group=>group.length))},(_,index)=>groups.flatMap(group=>group[index]?[group[index]]:[])).flat();
  const featured=groups.map(group=>group[0]).filter(Boolean).slice(0,3);
  const themes=testimonialThemes.flatMap(theme=>{
    const story=stories.find(item=>item.theme===theme.id&&item.category===theme.category)||stories.find(item=>item.theme===theme.id);
    return story?[{...theme,story}]:[];
  });
  return {stories,featured,themes,byId:new Map(stories.map(story=>[story.id,story]))};
}

export function openingExcerpt(story){
  return story.openingQuote || story.quote.match(/^.*?[.!?](?:\s|$)/)?.[0].trim() || story.quote;
}
