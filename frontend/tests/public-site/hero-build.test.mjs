import {test,expect} from 'vitest';
import {readFileSync} from 'node:fs';
import {publicPaths} from '../../src/site/page-metadata.mjs';
const read=(path,mode)=>readFileSync(new URL('../../dist/__booking_display/'+mode+'/'+(path==='/'?'index':path.slice(1))+'.html',import.meta.url),'utf8');
test.each(['/','/about'])('actual generated %s retains confirmed facts and the full public page in both modes',path=>{
 for(const mode of ['on','off']){
  const host=document.createElement('div');host.innerHTML=read(path,mode);
  expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelectorAll('main')).toHaveLength(1);expect(host.querySelector('[data-sarsa-static]')).toBeNull();
  expect(host.textContent).toContain('15+');expect(host.querySelectorAll('main section').length).toBeGreaterThan(5);
  expect(host.querySelector('[data-public-render]').dataset.publicMode).toBe(mode);
  expect(host.querySelectorAll('a[href="/booking"]').length>0).toBe(mode==='on');
  if(path==='/'){expect(host.querySelectorAll('.service-choices a')).toHaveLength(5);expect(host.querySelectorAll('.service')).toHaveLength(5);}
  else for(const text of ['Jyotish Shastri','Jyotish Acharya','Shri Vedang Jyotish Sansthan','Bhrigu Nandi Nadi Astrology','Yogrishi Astro Research Institute'])expect(host.textContent).toContain(text);
 }
});
test('all 12 ordinary routes use their actual components, without the retired short reading substitute',()=>{
 expect(publicPaths).toHaveLength(12);for(const path of publicPaths)for(const mode of ['on','off']){
  const html=read(path,mode);expect(html).not.toContain('data-sarsa-static');expect(html).not.toContain('Loading the page…');expect(html).toContain('data-public-path="'+path+'"');
 }
});
