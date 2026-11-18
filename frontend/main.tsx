import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import Wordmark from './VectorWordmark';
import Gallery from './CanvasGallery';
import VisualCarousel from './VisualCarousel';
import Magnet from './reactbits/Magnet';
import FadeContent from './reactbits/FadeContent';
import HalftoneReveal from './reactbits/HalftoneReveal';
import AccordionGallery from './reactbits/AccordionGallery';

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
 if(items.length){createRoot(container).render(<Gallery items={items} lang={lang} labels={galleryCopy}/>)}
}

const visualRoot=document.getElementById('visual-root'),visualData=document.getElementById('visual-data');
if(visualRoot&&visualData){try{const d=JSON.parse(visualData.textContent||'{}');if(d.photos?.length && !document.body.dataset.editMode){const lang=document.documentElement.lang as 'ru'|'en';if(d.mode==='accordion' && d.photos.length>1){createRoot(visualRoot).render(<AccordionGallery items={d.photos.map((p:any)=>({image:p.src,alt:p.alt[lang],label:(d.captions&&p.caption[lang])||p.alt[lang],link:p.src}))} accentColor="#ee514b" radius={0} tilt={0} parallax={0.15} grayscale={false} />)}else createRoot(visualRoot).render(<VisualCarousel photos={d.photos} captions={d.captions} closeLabel={d.close} previousLabel={d.previous} nextLabel={d.next} lang={lang}/>)}}catch(e){console.error('Visual:',e)}}

// Progressive enhancement: ordinary server-rendered links and images remain without JS.
if (!document.body.dataset.editMode) {
 const magnetRoot=document.getElementById('featured-magnet');
 const anchor=magnetRoot?.querySelector('a');
 if(magnetRoot&&anchor){const href=anchor.getAttribute('href')||'#',label=anchor.textContent||'';const active=matchMedia('(hover:hover) and (pointer:fine)').matches&&!matchMedia('(prefers-reduced-motion: reduce)').matches;createRoot(magnetRoot).render(<Magnet disabled={!active} magnetStrength={9} maxOffset={5} padding={10}><a className="button" href={href}>{label}</a></Magnet>)}
 const photoRoot=document.getElementById('about-photo-root');
 const link=photoRoot?.querySelector('a'),image=link?.querySelector('img');
 if(photoRoot&&link&&image){const src=image.getAttribute('src')||'',alt=image.alt,href=link.getAttribute('href')||'#',position=image.style.objectPosition;const fine=matchMedia('(hover:hover) and (pointer:fine)').matches&&!matchMedia('(prefers-reduced-motion: reduce)').matches;const halftone=photoRoot.dataset.halftone==='1'&&fine;createRoot(photoRoot).render(<FadeContent duration={0.5} initialOpacity={0.75}><a href={href} className="about-photo-preview"><img src={src} alt={alt} loading="lazy" style={{objectPosition:position}}/>{halftone&&<div className="halftone-layer" aria-hidden="true"><HalftoneReveal src={src} fit="cover" mode="mono" paperColor="#171716" inkColor="#e5e4df" cellSize={4} intro={false} clickBurst={false}/></div>}</a></FadeContent>)}
}
