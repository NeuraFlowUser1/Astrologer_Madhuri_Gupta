/** Focused compiled-output check. No server, provider or customer data access. */
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {resolve,relative} from 'node:path';
import {testimonialStories} from '../fixtures/testimonial-stories.mjs';
const dist=resolve(import.meta.dirname,'../../dist');
function files(directory){return readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?files(resolve(directory,entry.name)):[resolve(directory,entry.name)]);}
const entries=files(dist),manifest=JSON.parse(readFileSync(resolve(dist,'appointment-surface-manifest.json'),'utf8'));
// The general route must exist independently of the booking switch.
assert(manifest.public_paths.includes('/testimonials'));
assert(!manifest.booking_paths.includes('/testimonials'));
const pageAssets=Object.entries(manifest.assets).filter(([path])=>/\/Testimonials-/.test(path));
assert.equal(pageAssets.length,2);assert(pageAssets.every(([,owner])=>owner==='general'));
for(const mode of ['on','off']){
  const html=readFileSync(resolve(dist,`__booking_display/${mode}/testimonials.html`),'utf8');
  assert.match(html,/<title>Customer reviews \| Sarsa Jyotish Sansthan<\/title>/);
  assert.match(html,/https:\/\/www\.sarsajyotishsansthan\.com\/testimonials/);
  assert.match(html,new RegExp(`booking-display-mode" content="${mode}"`));
  assert.match(readFileSync(resolve(dist,`__booking_display/${mode}/sitemap.xml`),'utf8'),/\/testimonials<\/loc>/);
}
const scripts=entries.filter(path=>/\.(?:js|html)$/.test(path)).map(path=>readFileSync(path,'utf8')).join('\n');
for(const story of testimonialStories){assert(!scripts.includes(story.name),'Invented identity appeared in compiled public output: '+story.name);assert(!scripts.includes(story.quote),'Invented quotation appeared in compiled public output.');}
assert(entries.every(path=>!/(?:^|\/)(?:tests|fixtures|preview)(?:\/|$)/.test(relative(dist,path))),'Private harness appeared in compiled public output.');
assert(!scripts.includes('Private Testimonials integration review'));
assert(!scripts.includes('Private Customer reviews integration review'));
assert(!scripts.includes('Private About certificates design review'));
for(const id of ['jyotish-shastri','jyotish-acharya','astro-research-institute','trinity-vaastu-numerology']){
 for(const file of [`${id}-preview.webp`,`${id}-full.webp`,`${id}-original.${id==='astro-research-institute'?'pdf':'jpeg'}`]){
  assert.equal(manifest.assets['/media/certificates/'+file],'general','Certificate must remain public independently of booking.');
 }
}
console.log(JSON.stringify({route:'/testimonials',modes:2,privateFixtureRecordsExcluded:testimonialStories.length,privateHarnessExcluded:true,compiledFilesChecked:entries.length,result:'passed'}));
