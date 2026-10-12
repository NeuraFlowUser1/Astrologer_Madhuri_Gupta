/** Course facts transcribed from the four supplied certificates; no degree claims. */
const media='/media/certificates/';
export const certificates=Object.freeze([
  {id:'jyotish-shastri',title:'Jyotish Shastri',issuer:'Shri Vedang Jyotish Sansthan',period:'2010–11 course · Certificate dated 31 July 2011',explanation:'Study in traditional Indian astrology, also called Jyotish. This is the first of the two Jyotish courses shown here.',orientation:'portrait',width:1066,height:1475},
  {id:'jyotish-acharya',title:'Jyotish Acharya',issuer:'Shri Vedang Jyotish Sansthan',period:'2011–12 course · Certificate dated 23 August 2012',explanation:'Further study in traditional astrology, following her earlier Jyotish Shastri course.',orientation:'portrait',width:1096,height:1435},
  {id:'astro-research-institute',title:'Bhrigu Nandi Nadi Astrology',issuer:'Yogrishi Astro Research Institute',period:'Certificate dated 5 September 2022',explanation:'Additional training in Bhrigu Nandi Nadi, a branch of astrology. This certificate records completion of that course.',orientation:'landscape',width:1491,height:1055},
  {id:'trinity-vaastu-numerology',title:'Basic Numerology Foundation Session',issuer:'Trinity Vaastu · Saarthi Sahil Jain',period:'Two-day online session',explanation:'A foundation session on numerology—the use of names and numbers in readings.',orientation:'landscape',width:1491,height:1055},
].map(certificate=>Object.freeze({...certificate,
  thumbnail:media+certificate.id+'-preview.webp',full:media+certificate.id+'-full.webp',
  original:media+certificate.id+'-original.'+(certificate.id==='astro-research-institute'?'pdf':'jpeg'),
})));
