import {test,expect} from 'vitest';
import {buildTestimonialIndex,openingExcerpt,testimonialServices} from '../../src/site/testimonials-model.mjs';
import {clientTestimonials} from '../../src/site/testimonials-content.mjs';
import {testimonialStories} from '../fixtures/testimonial-stories.mjs';
test('editorial index interleaves four services, selects distinct voices and preserves every source record',()=>{
  const index=buildTestimonialIndex(testimonialStories);
  expect(index.stories).toHaveLength(12);expect(new Set(index.stories)).toEqual(new Set(testimonialStories));
  expect(index.stories.slice(0,4).map(story=>story.category)).toEqual(testimonialServices.map(service=>service.id));
  expect(index.featured.map(story=>story.category)).toEqual(testimonialServices.slice(0,3).map(service=>service.id));
  expect(index.themes.map(theme=>theme.story.id)).toEqual(['neha-numerology','rohit-vastu','kavya-matching']);
  expect(index.byId.get('radhika-prediction')).toBe(testimonialStories[0]);
});
test('sparse real feedback works without fabricated filler, including a lone Numerology client',()=>{
  const story={...testimonialStories[9],theme:undefined};
  const sparse=buildTestimonialIndex([story]);expect(sparse.stories).toEqual([story]);expect(sparse.featured).toEqual([story]);expect(sparse.themes).toEqual([]);
  const fallback={...story,theme:'calm'};expect(buildTestimonialIndex([fallback]).themes[0].story).toBe(fallback);
  expect(buildTestimonialIndex([])).toEqual({stories:[],featured:[],themes:[],byId:new Map()});
});
test('the approved twelve-account public source is immutable and shared by the test alias',()=>{
  expect(clientTestimonials).toBe(testimonialStories);expect(clientTestimonials).toHaveLength(12);
  expect(Object.isFrozen(clientTestimonials)).toBe(true);
  for(const story of clientTestimonials){
    expect(Object.isFrozen(story)).toBe(true);expect(Object.isFrozen(story.paragraphs)).toBe(true);
    expect(story).not.toHaveProperty('fictional');
  }
  for(const service of testimonialServices)expect(clientTestimonials.filter(story=>story.category===service.id)).toHaveLength(3);
});
test.each([
  null,{id:''},{...testimonialStories[0],id:7},{...testimonialStories[0],category:'unknown'},
  {...testimonialStories[0],name:' '},{...testimonialStories[0],city:7},
  {...testimonialStories[0],paragraphs:null},{...testimonialStories[0],paragraphs:[]},
  {...testimonialStories[0],paragraphs:['']},{...testimonialStories[0],paragraphs:[42]},
])('malformed editorial record fails explicitly: %j',story=>{
  expect(()=>buildTestimonialIndex([story])).toThrow('Invalid testimonial content');
});
test('duplicate IDs fail instead of opening another client account',()=>{
  expect(()=>buildTestimonialIndex([testimonialStories[0],testimonialStories[0]])).toThrow('unique IDs');
});
test('opening excerpts retain approved wording and derive only complete first sentences otherwise',()=>{
  expect(openingExcerpt(testimonialStories[0])).toBe('Pehli baar laga ki kisi ne meri baat poori suni.');
  expect(openingExcerpt({quote:'Thank you! I felt heard.'})).toBe('Thank you!');
  expect(openingExcerpt({quote:'No punctuation in this account'})).toBe('No punctuation in this account');
});
