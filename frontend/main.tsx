import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import Wordmark from './VectorWordmark';
import Gallery from './FiniteGallery';
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
 if(items.length){createRoot(container).render(<Gallery items={items} lang={lang} labels={galleryCopy}/>)}
}

const visualRoot=document.getElementById('visual-root'),visualData=document.getElementById('visual-data');
if(visualRoot&&visualData){try{const d=JSON.parse(visualData.textContent||'{}');if(d.photos?.length)createRoot(visualRoot).render(<VisualCarousel photos={d.photos} captions={d.captions} closeLabel={d.close} previousLabel={d.previous} nextLabel={d.next} lang={document.documentElement.lang as 'ru'|'en'}/>)}catch(e){console.error('Visual:',e)}}
