import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import Wordmark from './VectorWordmark';
import Gallery from './InfiniteGallery';
import VisualCarousel from './VisualCarousel';

const wm=document.getElementById('wordmark-root');
if(wm){
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 if(!reduce){createRoot(wm).render(<Wordmark text="  ACOULBOT  " handles={{size:109,labels:false,spread:27}} style={{minWidth:0,minHeight:0,width:'100%',height:'100%',background:'transparent'}}/>);
 requestAnimationFrame(()=>requestAnimationFrame(()=>{const c=wm.querySelector('canvas');if(c&&(c.getContext('webgl2')||c.getContext('webgl')))wm.classList.add('ready')}));}
}
const container=document.getElementById('gallery-root');
const data=document.getElementById('projects-data');
if(container && data){
 let items:any[]=[];try{items=JSON.parse(data.textContent||'[]')}catch{}
 const lang=document.documentElement.lang;
 const mobile=matchMedia('(max-width: 800px)').matches;
 const galleryCopy=JSON.parse(document.getElementById('gallery-copy')?.textContent||'{}');
 const fallback=['#322c2a','#262a29','#323132','#3a302c'];
 function placeholder(i:number){let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="360" height="440"><rect width="360" height="440" fill="${fallback[i%4]}"/><path d="M70 300 L180 90 L290 300 M105 235 H255" fill="none" stroke="#a7a39d" stroke-opacity=".45" stroke-width="1"/><circle cx="180" cy="205" r="90" fill="none" stroke="#c95952" stroke-opacity=".55"/></svg>`;return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg)}
 const images=items.map((p,i)=>({src:p.cover||placeholder(i),alt:p.title[lang],title:p.title[lang],category:p.category[lang],href:'/'+lang+'/project/'+p.slug}));
 if(images.length){
  function Canvas(){const [active,setActive]=React.useState(false);return <>{createPortal(<button className="touch-toggle" aria-pressed={active} onClick={()=>setActive(!active)}>{active?galleryCopy.off:galleryCopy.on}</button>,document.getElementById('gallery-controls')!)}<Gallery images={images} density={mobile?12:5} imageWidth={mobile?135:190} imageHeight={mobile?160:225} rounded={0} dragSpeed={20} driftAmount={8} friction={10} backgroundColor="#101010" touchEnabled={active} style={{width:'100%',height:'100%',minWidth:0,minHeight:0}} /></>}
  createRoot(container).render(<Canvas/>);
 }
}

const visualRoot=document.getElementById('visual-root'),visualData=document.getElementById('visual-data');
if(visualRoot&&visualData){try{const d=JSON.parse(visualData.textContent||'{}');if(d.photos?.length)createRoot(visualRoot).render(<VisualCarousel photos={d.photos} captions={d.captions} closeLabel={d.close} previousLabel={d.previous} nextLabel={d.next} lang={document.documentElement.lang as 'ru'|'en'}/>)}catch(e){console.error('Visual:',e)}}
