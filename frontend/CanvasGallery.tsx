import * as React from 'react';
import InfiniteGallery from './InfiniteGallery';
type Item={src:string;fit:'cover'|'contain';slug:string;title:Record<string,string>;category:Record<string,string>};
export default function CanvasGallery({items,lang,labels}:{items:Item[];lang:string;labels:Record<string,string>}){
 const [touch,setTouch]=React.useState(false),[version,setVersion]=React.useState(0);
 const mobile=matchMedia('(max-width: 800px)').matches;
 const images=React.useMemo(()=>items.map(p=>({src:p.src||'',fit:p.fit||'contain',title:p.title[lang],category:p.category[lang],href:'/'+lang+'/project/'+p.slug})),[items,lang]);
 function reset(){try{sessionStorage.removeItem('ac-gallery-v5')}catch{}setVersion(v=>v+1)}
 return <div className="free-canvas"><div className="canvas-actions"><span className="canvas-instruction">{labels.hint}</span><div><button className="canvas-touch" type="button" aria-pressed={touch} onClick={()=>setTouch(!touch)}>{touch?labels.off:labels.on}</button><button type="button" onClick={reset}>{labels.reset} ↗</button></div></div><InfiniteGallery key={version} className="infinite-canvas" images={images} density={mobile?12:8} imageWidth={mobile?160:230} imageHeight={mobile?190:270} rounded={0} dragSpeed={20} driftAmount={8} friction={10} backgroundColor="transparent" touchEnabled={touch} height={mobile?540:'clamp(500px,60vw,720px)'} /></div>
}
