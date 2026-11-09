// Adapted from the user-provided Originkit Magnetic Carousel: eased proximity
// magnification, with local images, keyboard-accessible controls and responsive viewing.
import * as React from 'react';
import {useEffect,useRef,useState} from 'react';

type Photo={src:string,alt:{ru:string,en:string},caption:{ru:string,en:string},focus_x:number,focus_y:number};
export default function VisualCarousel({photos,captions,closeLabel,previousLabel,nextLabel,lang}:{photos:Photo[],captions:boolean,closeLabel:string,previousLabel:string,nextLabel:string,lang:'ru'|'en'}){
 const track=useRef<HTMLDivElement>(null),dialog=useRef<HTMLDialogElement>(null),raf=useRef(0),current=useRef<number[]>(photos.map(()=>0)),target=useRef<number[]>(photos.map(()=>0));
 const [factors,setFactors]=useState<number[]>(photos.map(()=>0));const [selected,setSelected]=useState<number|null>(null);const [width,setWidth]=useState(0);
 const mobile=matchMedia('(max-width: 800px)').matches;const hover=matchMedia('(hover:hover) and (pointer:fine)').matches;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const base=mobile?88:100, expanded=mobile?88:180, height=mobile?260:340,gap=mobile?10:14;
 useEffect(()=>{let el=track.current;if(!el)return;let ro=new ResizeObserver(()=>setWidth(el!.clientWidth));ro.observe(el);setWidth(el.clientWidth);return()=>ro.disconnect()},[]);
 useEffect(()=>()=>cancelAnimationFrame(raf.current),[]);
 const ease=()=>{if(raf.current)return;const step=()=>{let moving=false;current.current=current.current.map((v,i)=>{let d=(target.current[i]||0)-v;if(Math.abs(d)<.001)return target.current[i]||0;moving=true;return v+d*.2});setFactors([...current.current]);raf.current=moving?requestAnimationFrame(step):0};raf.current=requestAnimationFrame(step)};
 const onMove=(e:React.MouseEvent)=>{if(!hover||reduced||selected!==null||!track.current)return;let el=track.current,rect=el.getBoundingClientRect();let size=photos.length*base+(photos.length-1)*gap;let offset=Math.max(0,(rect.width-size)/2);let x=e.clientX-rect.left+el.scrollLeft;target.current=photos.map((_,i)=>{let center=offset+i*(base+gap)+base/2, f=Math.max(0,1-Math.abs(x-center)/200);return f*f*(3-2*f)});ease()};
 const onLeave=()=>{target.current=photos.map(()=>0);ease()};
 function open(i:number){setSelected(i);onLeave();dialog.current?.showModal()}
 function close(){dialog.current?.close();setSelected(null)}
 const shift=(n:number)=>setSelected(i=>i===null?i:(i+n+photos.length)%photos.length)
 const selectedPhoto=selected===null?null:photos[selected];const fits=photos.length*base+(photos.length-1)*gap<=width;
 return <><div ref={track} className={'magnetic-track'+(selected!==null?' is-open':'')} onMouseMove={onMove} onMouseLeave={onLeave} style={{justifyContent:fits?'center':'flex-start',gap}}>
  {photos.map((im,i)=><button key={i} type="button" className="magnetic-image" aria-label={im.alt[lang]} onClick={()=>open(i)} style={{width:base+(expanded-base)*(factors[i]||0),height:height+(mobile?0:55*(factors[i]||0))}}><img src={im.src} alt="" loading="lazy" draggable={false} style={{objectPosition:`${im.focus_x}% ${im.focus_y}%`}}/>{captions&&im.caption[lang]&&<span>{im.caption[lang]}</span>}</button>)}
 </div><dialog className="visual-dialog" ref={dialog} onCancel={()=>setSelected(null)} onClose={()=>setSelected(null)} onClick={e=>{if(e.target===dialog.current||(e.target as HTMLElement).classList.contains('visual-viewer'))close()}} onKeyDown={e=>{if(e.key==='ArrowRight'){e.preventDefault();shift(1)}if(e.key==='ArrowLeft'){e.preventDefault();shift(-1)}}}><div className="visual-viewer"><button className="visual-close" type="button" onClick={close} aria-label={closeLabel}>{closeLabel} ×</button>{selectedPhoto&&<><img src={selectedPhoto.src} alt={selectedPhoto.alt[lang]}/>{captions&&selectedPhoto.caption[lang]&&<p>{selectedPhoto.caption[lang]}</p>}{photos.length>1&&<div className="visual-navigation"><button type="button" aria-label={previousLabel} onClick={()=>shift(-1)}>←</button><button type="button" aria-label={nextLabel} onClick={()=>shift(1)}>→</button></div>}</>}</div></dialog></>
}
