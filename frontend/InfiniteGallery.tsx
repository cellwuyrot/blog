/* eslint-disable */
// Infinity Canvas — Originkit

"use client"

const useIsStaticRenderer = () => false
import { useMotionValue } from "framer-motion"
import * as React from "react"
import { useEffect, useMemo, useRef } from "react"

// Official prop schema:
//   { url, width, height } — intrinsic dims kept for the image array, but tile
//   footprint is now driven by imageWidth/imageHeight (fixed box, cover-fit).
type GalleryImage = { src: string; srcSet?: string; fit?: "cover" | "contain"; alt?: string; href?: string; title?: string; category?: string }

interface InfiniteGalleryProps {
    width?: string | number
    height?: string | number
    className?: string
    images: GalleryImage[]
    density: number
    imageWidth: number
    imageHeight: number
    rounded: number
    dragSpeed: number
    driftAmount: number
    friction: number
    backgroundColor: string
    style?: React.CSSProperties
    touchEnabled?: boolean
}

const DEFAULT_IMAGES: GalleryImage[] = [
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/612d1402-0ad9-4135-3bbc-a30a6a252b00/w=800",
        alt: "Coverflow card 1",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/6d2ad64a-102d-4eab-0efe-31479e34b500/w=800",
        alt: "Coverflow card 2",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/be854dd1-37aa-4fc7-f569-fdb948109300/w=800",
        alt: "Coverflow card 3",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/51984031-9176-484b-f5e0-4af9a8e9ed00/w=800",
        alt: "Coverflow card 4",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/34ce1842-4b7a-4d52-0302-38582c341700/w=800",
        alt: "Coverflow card 5",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/88369c6d-00cc-4ac9-74ca-0f0965e06300/w=800",
        alt: "Coverflow card 6",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/aeaa0756-9647-4f6c-d900-204bd25e4a00/w=800",
        alt: "Coverflow card 7",
    },
    {
        src: "https://imagedelivery.net/IEUjvl3YUlxY-MrTpOAWDQ/316d1761-fd79-4ca9-b8d4-f2bb20521a00/w=800",
        alt: "Coverflow card 8",
    },
]

// ---- deterministic PRNG infrastructure --------------------------------------

// Mix three integer coordinates + a salt into a uint32. Used to seed each cell.
// Based on the integer hash from "Optimized Spatial Hashing for Collision
// Detection of Deformable Objects" (Teschner et al.) with extra avalanching.
function hash3(cx: number, cy: number, cz: number, salt: number) {
    let h = (cx | 0) * 0x8da6b343
    h ^= Math.imul(cy | 0, 0xd8163841)
    h ^= Math.imul(cz | 0, 0xcb1ab31f)
    h ^= salt | 0
    h ^= h >>> 16
    h = Math.imul(h, 0x7feb352d)
    h ^= h >>> 15
    h = Math.imul(h, 0x846ca68b)
    h ^= h >>> 16
    return h >>> 0
}

// mulberry32 — small, fast, good enough for layout jitter.
function mulberry32(seed: number) {
    let a = seed >>> 0
    return () => {
        a = (a + 0x6d2b79f5) >>> 0
        let t = a
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}

// Linear interpolation toward target with frame-rate-independent smoothing.
// `t` is a 0..1 weight applied per frame; we run at ~60fps so 0.1–0.2 feels right.
function lerp(a: number, b: number, t: number) {
    return a + (b - a) * t
}

// One tile, deterministically derived from its cell + slot index + octave.
// bakedScale is an intrinsic depth property assigned once at scatter time and
// never recomputed on scroll. Within a single octave layer, every tile
// transforms by the same global scale factor — this eliminates the "dance".
type Tile = {
    // World-space center (in world units, in this octave's coordinate frame).
    wx: number
    wy: number
    // Cell + slot + octave identity (used as a stable DOM key).
    cx: number
    cy: number
    slot: number
    octave: number
    // Image index into the images array.
    imgIdx: number
    // Rendered footprint in world units (imageWidth/imageHeight ÷ PX_PER_UNIT).
    w: number
    h: number
    // Small layout-stable rotation in degrees.
    rot: number
    // Intrinsic aesthetic depth. Multiplied by the octave's effective scale to
    // get the final on-screen scale. Drawn from [scaleMin, scaleMax] at scatter
    // time — small values look "further away", larger values look "closer".
    bakedScale: number
}

// Pixel-per-world-unit. World units are abstract; we render at this scale.
const PX_PER_UNIT = 6

// Grid cell size in world units. Fixed internally (no longer a control); drives
// the statistical spacing/density of the scattered tiles.
const CELL_SIZE = 110

// Safety cap on how many cells we step out from the camera per axis, so a small
// layer scale can't request an unbounded grid.
const MAX_RANGE = 20

/**
 * InfiniteGallery — flat-plane infinite gallery with TRUE infinite zoom.
 *
 * Zoom model — "octave-swap":
 *
 *  - The user input drives `logZoom`, a free-ranging scalar that accumulates
 *    from the wheel (positive = zooming in). Effective zoom = 2^logZoom.
 *  - At any moment we pick the "current" octave = floor(logZoom), and the
 *    fractional remainder frac = logZoom - octave is in [0, 1).
 *  - Candidates come from the original scattered octave grids; only one
 *    on-screen instance per image is chosen. A selected occurrence is kept
 *    until it leaves view or becomes too small/large to be useful. It can then
 *    reappear at another depth. Zoom itself has no fixed hard stop.
 *
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 * @framerIntrinsicWidth 600
 * @framerIntrinsicHeight 600
 */
export default function InfiniteGallery(props: InfiniteGalleryProps) {
    props = { ...COMPONENT_DEFAULTS, ...props }
    const {
        width,
        height,
        className,
        images,
        density,
        imageWidth,
        imageHeight,
        rounded,
        dragSpeed,
        driftAmount,
        friction,
        backgroundColor,
        style,
        touchEnabled,
    } = props

    const containerRef = useRef<HTMLDivElement | null>(null)
    const sceneRef = useRef<HTMLDivElement | null>(null)
    const isStatic = useIsStaticRenderer()

    // Clamp props into their official ranges.
    const safeImages =
        Array.isArray(images) && images.length > 0 ? images : DEFAULT_IMAGES
    const safeDensity = Math.max(1, Math.min(15, Math.floor(density || 5)))
    const safeImageWidth = Math.max(8, Math.min(4000, imageWidth || 150))
    const safeImageHeight = Math.max(8, Math.min(4000, imageHeight || 150))
    const safeRounded = Math.max(0, Math.min(20, rounded ?? 3))
    // Sliders carry whole-number panel values; divide back to working ranges.
    const safeDragSpeed = Math.max(0.1, Math.min(5, (dragSpeed || 20) / 20))
    const safeDriftAmount = Math.max(0, Math.min(20, driftAmount ?? 8))
    // Friction 1..20 → per-frame velocity RETENTION. 1 = least friction (glides
    // on, retention ~0.985), 20 = most friction (stops quickly, retention 0.7).
    const safeFriction =
        1 - (Math.max(1, Math.min(20, friction ?? 10)) / 20) * 0.3

    // ---- Camera & input state (motion values; no React re-renders per frame) -

    const saved = useMemo(() => { try { return JSON.parse(sessionStorage.getItem("ac-gallery-v5") || "null") || {} } catch { return {} } }, [])
    const initial = (key: string) => typeof saved[key] === "number" && Number.isFinite(saved[key]) ? saved[key] : 0
    const targetX = useMotionValue(initial("x"))
    const targetY = useMotionValue(initial("y"))
    const camX = useMotionValue(initial("x"))
    const camY = useMotionValue(initial("y"))
    const velX = useMotionValue(0)
    const velY = useMotionValue(0)

    const targetLogZoom = useMotionValue(initial("zoom"))
    const logZoom = useMotionValue(initial("zoom"))
    const velLogZoom = useMotionValue(0)

    const driftTX = useMotionValue(0)
    const driftTY = useMotionValue(0)
    const driftX = useMotionValue(0)
    const driftY = useMotionValue(0)

    // ---- Cell generation -----------------------------------------------------

    const subN = Math.max(1, Math.ceil(Math.sqrt(safeDensity)))
    const subSize = CELL_SIZE / subN
    const SUBCELL_INNER_PAD = 0.1
    const effectivePerCell = Math.min(safeDensity, subN * subN)

    const imagesCount = safeImages.length

    const SCALE_MIN = 0.45
    const SCALE_MAX = 1.6

    const generateCell = useMemo(() => {
        return (gx: number, gy: number, octave: number): Tile[] => {
            const seed = hash3(gx, gy, octave | 0, 0x9e3779b1)
            const rand = mulberry32(seed)

            const totalSubs = subN * subN
            const subs = new Array<number>(totalSubs)
            for (let i = 0; i < totalSubs; i++) subs[i] = i
            for (let i = totalSubs - 1; i > 0; i--) {
                const j = Math.floor(rand() * (i + 1))
                const tmp = subs[i]
                subs[i] = subs[j]
                subs[j] = tmp
            }

            const tiles: Tile[] = []
            const count = Math.min(effectivePerCell, totalSubs)

            const pad = subSize * SUBCELL_INNER_PAD
            const innerRange = Math.max(0, subSize - pad * 2)

            const cellX0 = gx * CELL_SIZE
            const cellY0 = gy * CELL_SIZE

            // Fixed tile box (cover-fit), converted to world units.
            const wWorld = safeImageWidth / PX_PER_UNIT
            const hWorld = safeImageHeight / PX_PER_UNIT

            for (let slot = 0; slot < count; slot++) {
                const subIdx = subs[slot]
                const sx = subIdx % subN
                const sy = Math.floor(subIdx / subN)

                const wx = cellX0 + sx * subSize + pad + rand() * innerRange
                const wy = cellY0 + sy * subSize + pad + rand() * innerRange

                const bakedScale = SCALE_MIN + rand() * (SCALE_MAX - SCALE_MIN)

                const imgIdx =
                    imagesCount > 0
                        ? Math.floor(rand() * imagesCount) % imagesCount
                        : 0

                tiles.push({
                    wx,
                    wy,
                    cx: gx,
                    cy: gy,
                    slot,
                    octave,
                    imgIdx,
                    w: wWorld,
                    h: hWorld,
                    rot: 0,
                    bakedScale,
                })
            }

            return tiles
        }
    }, [
        safeImages,
        imagesCount,
        safeImageWidth,
        safeImageHeight,
        subN,
        subSize,
        effectivePerCell,
    ])

    // ---- Per-frame loop -----------------------------------------------------

    useEffect(() => {
        const scene = sceneRef.current
        const container = containerRef.current
        if (!scene) return

        // Cache the container size; the visible cell range is derived from it so
        // the whole screen is always filled (no fixed "view range").
        let cW = container ? container.clientWidth || 900 : 900
        let cH = container ? container.clientHeight || 600 : 600
        const ro = new ResizeObserver(() => {
            if (container) {
                cW = container.clientWidth || cW
                cH = container.clientHeight || cH
            }
        })
        if (container) ro.observe(container)

        // One physical element per image. Its placement remains stable while it
        // is visible. When it leaves the view, it can reappear at a new depth.
        type Draw = { el: HTMLDivElement; img: HTMLImageElement | null; tile: Tile | null; x: number; y: number; scale: number; opacity: number }
        const nodes = new Map<number, Draw>()
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        const keyOf = (t: Tile) => `${t.octave}:${t.cx}:${t.cy}:${t.slot}`
        const getNode = (idx:number):Draw => {
            const previous=nodes.get(idx); if(previous) return previous
            const src=safeImages[idx]
            const el=document.createElement("div")
            el.className="inf-card"+(src.fit === "contain" ? " inf-card--contain" : "")+(!src.src ? " inf-card--empty" : "")
            Object.assign(el.style,{position:"absolute",left:"50%",top:"50%",transformOrigin:"0 0",willChange:"transform, opacity",pointerEvents:"auto"})
            el.dataset.href=src.href || "";el.dataset.imageIndex=String(idx)
            el.setAttribute("role","link");el.setAttribute("aria-label",src.title || src.alt || "Project")
            el.addEventListener("click",(e)=>{if(!touchEnabled && matchMedia("(pointer: coarse)").matches && e.detail && el.dataset.href){sessionStorage.setItem("ac-gallery-v5",JSON.stringify({x:targetX.get(),y:targetY.get(),zoom:targetLogZoom.get()}));window.location.assign(el.dataset.href)}})
            el.addEventListener("keydown",e=>{if(e.key==="Enter" && el.dataset.href){sessionStorage.setItem("ac-gallery-v5",JSON.stringify({x:targetX.get(),y:targetY.get(),zoom:targetLogZoom.get()}));window.location.assign(el.dataset.href)}})
            let img:HTMLImageElement|null=null
            if(src.src){img=document.createElement("img");img.src=src.src;if(src.srcSet)img.srcset=src.srcSet;img.alt="";img.draggable=false;Object.assign(img.style,{width:"100%",height:"100%",objectFit:src.fit === "contain" ? "contain" : "cover",display:"block",pointerEvents:"none",userSelect:"none"});el.appendChild(img)}
            else {let art=document.createElement("span");art.className="inf-placeholder";art.setAttribute("aria-hidden","true");art.textContent="↗";el.appendChild(art)}
            const caption=document.createElement("span");caption.className="inf-caption";const category=document.createElement("small"),title=document.createElement("strong");category.textContent=src.category || "";title.textContent=src.title || "";caption.append(category,title);el.appendChild(caption)
            if(src.fit === "contain" && img){const image=img;const positionCaption=()=>{if(!image.naturalWidth || !image.naturalHeight)return;const drawnHeight=Math.min(safeImageHeight,safeImageWidth*image.naturalHeight/image.naturalWidth);caption.style.top=`${(safeImageHeight+drawnHeight)/2}px`};image.addEventListener("load",positionCaption,{once:true});if(image.complete)positionCaption()}
            scene.appendChild(el);let draw:Draw={el,img,tile:null,x:0,y:0,scale:1,opacity:0};nodes.set(idx,draw);return draw
        }
        type Projection={tile:Tile; x:number;y:number;scale:number;width:number;height:number}
        const projectTile = (t:Tile,lz:number,cx:number,cy:number):Projection|null => {
            let exp=lz-t.octave;if(exp < -20 || exp > 20)return null
            const layerScale=Math.pow(2,exp),scale=t.bakedScale*layerScale,width=t.w*PX_PER_UNIT,height=t.h*PX_PER_UNIT
            const x=(t.wx-cx)*layerScale*PX_PER_UNIT,y=(t.wy-cy)*layerScale*PX_PER_UNIT
            if(!Number.isFinite(x+y+scale))return null
            // Wait until a thumbnail is offscreen, too small, or has grown far
            // beyond the viewport before selecting another occurrence.
            if(width*scale < 5 || height*scale < 5 || width*scale > cW*4 || height*scale > cH*4)return null
            if(Math.abs(x)>cW/2+width*scale/2+16 || Math.abs(y)>cH/2+height*scale/2+40)return null
            return {tile:t,x,y,scale,width,height}
        }
        const candidates = (octave:number,lz:number,cx:number,cy:number):Projection[] => {
            const layerScale=Math.pow(2,lz-octave),camCellX=Math.floor(cx/CELL_SIZE),camCellY=Math.floor(cy/CELL_SIZE)
            const rangeX=Math.min(MAX_RANGE,Math.ceil(cW/2/(PX_PER_UNIT*layerScale)/CELL_SIZE)+1)
            const rangeY=Math.min(MAX_RANGE,Math.ceil(cH/2/(PX_PER_UNIT*layerScale)/CELL_SIZE)+1)
            const out:Projection[]=[]
            for(let dy=-rangeY;dy<=rangeY;dy++)for(let dx=-rangeX;dx<=rangeX;dx++)for(const t of generateCell(camCellX+dx,camCellY+dy,octave)){const p=projectTile(t,lz,cx,cy);if(p)out.push(p)}
            return out
        }
        const project=()=>{
            const cx=camX.get(),cy=camY.get(),lz=logZoom.get(),octave=Math.floor(lz)
            const choices=new Map<number,Projection>()
            // Retain each existing occurrence as long as it remains visible.
            for(const [idx,node] of nodes){if(node.tile){const p=projectTile(node.tile,lz,cx,cy);if(p)choices.set(idx,p)}}
            // Reuse the reference's scattered cells / octaves but choose only
            // one occurrence per image across BOTH layers and the whole frame.
            const nearby=choices.size<imagesCount ? [...candidates(octave,lz,cx,cy),...candidates(octave+1,lz,cx,cy)] : []
            const byImage=new Map<number,Projection[]>()
            for(const p of nearby){if(choices.has(p.tile.imgIdx))continue;const list=byImage.get(p.tile.imgIdx)||[];list.push(p);byImage.set(p.tile.imgIdx,list)}
            for(const [idx,list] of byImage){let best:Projection|null=null,bestScore=Infinity
                for(const p of list){let w=p.width*p.scale,h=p.height*p.scale
                    // Prefer wholly visible items and leave breathing room; do not
                    // pull every newly introduced image into the same centre.
                    let score=.55*Math.hypot(p.x/(cW||1),p.y/(cH||1))
                    score+=Math.max(0,(Math.abs(p.x)+w/2-cW/2)/(cW||1))*5+Math.max(0,(Math.abs(p.y)+h/2-cH/2)/(cH||1))*5
                    for(const q of choices.values()){const dx=Math.abs(p.x-q.x),dy=Math.abs(p.y-q.y),rw=(w+q.width*q.scale)/2+28,rh=(h+q.height*q.scale)/2+38;score+=Math.max(0,1-dx/rw)*Math.max(0,1-dy/rh)*15}
                    if(score<bestScore){best=p;bestScore=score}
                }
                if(best)choices.set(idx,best)
            }
            for(const [idx,p] of choices){const n=getNode(idx),changed=!n.tile||keyOf(n.tile)!==keyOf(p.tile);n.tile=p.tile
                if(changed){n.x=p.x;n.y=p.y;n.scale=p.scale;n.opacity=0}
                else {n.x=p.x;n.y=p.y;n.scale=p.scale}
                const size=Math.min(p.width*p.scale,p.height*p.scale);const large=Math.max(p.width*p.scale/(cW||1),p.height*p.scale/(cH||1))
                const target=Math.min(1,Math.max(0,(size-5)/22),Math.max(0,(4-large)*1.3));n.opacity=reduced?target:lerp(n.opacity,target,.16)
                n.el.style.width=`${p.width}px`;n.el.style.height=`${p.height}px`
                n.el.style.transform=`translate3d(${n.x}px, ${n.y}px, 0) scale(${n.scale}) translate(${-p.width/2}px, ${-p.height/2}px)`
                n.el.style.opacity=String(n.opacity);n.el.style.zIndex=String(Math.round(p.tile.bakedScale*100));n.el.tabIndex=n.opacity>.4?0:-1;n.el.style.pointerEvents=n.opacity>.4?"auto":"none"
                if(n.img)n.img.style.borderRadius=`${(safeRounded/20)*(Math.min(p.width,p.height)/2)}px`
            }
            for(const [idx,n] of nodes)if(!choices.has(idx)){n.tile=null;n.opacity=reduced?0:lerp(n.opacity,0,.16);n.el.style.opacity=String(n.opacity);n.el.tabIndex=-1;n.el.style.pointerEvents="none";if(n.opacity<.01){n.el.remove();nodes.delete(idx)}}
        }
        const disposeAllLayers=()=>{for(const n of nodes.values())n.el.remove();nodes.clear()}

        project()
        if (isStatic) {
            ro.disconnect()
            return
        }

        let raf = 0
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        let visible = true
        const io = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true })
        if (container) io.observe(container)

        const loop = () => {
            if (!visible || document.hidden) { raf = requestAnimationFrame(loop); return }
            if (reducedMotion) {
                velX.set(0); velY.set(0); velLogZoom.set(0)
                camX.set(targetX.get()); camY.set(targetY.get()); logZoom.set(targetLogZoom.get())
                project(); raf = requestAnimationFrame(loop); return
            }
            // 1) Apply XY velocity (drag inertia) with friction decay.
            const tx = targetX.get() + velX.get()
            const ty = targetY.get() + velY.get()
            targetX.set(tx)
            targetY.set(ty)
            velX.set(velX.get() * safeFriction)
            velY.set(velY.get() * safeFriction)

            const vlz = velLogZoom.get()
            if (vlz !== 0) {
                targetLogZoom.set(targetLogZoom.get() + vlz)
                velLogZoom.set(vlz * safeFriction)
            }

            // 2) Smooth drift toward mouse-parallax target.
            driftX.set(
                lerp(driftX.get(), driftTX.get() * safeDriftAmount, 0.08)
            )
            driftY.set(
                lerp(driftY.get(), driftTY.get() * safeDriftAmount, 0.08)
            )

            // 3) Smooth cam toward target (+ drift), logZoom toward target.
            camX.set(lerp(camX.get(), targetX.get() + driftX.get(), 0.18))
            camY.set(lerp(camY.get(), targetY.get() + driftY.get(), 0.18))
            logZoom.set(lerp(logZoom.get(), targetLogZoom.get(), 0.18))

            project()
            raf = requestAnimationFrame(loop)
        }
        raf = requestAnimationFrame(loop)
        return () => {
            cancelAnimationFrame(raf)
            io.disconnect()
            ro.disconnect()
            disposeAllLayers()
        }
    }, [
        generateCell,
        touchEnabled,
        safeFriction,
        safeDriftAmount,
        safeRounded,
        safeImages,
        isStatic,
        camX,
        camY,
        logZoom,
        targetX,
        targetY,
        targetLogZoom,
        velX,
        velY,
        velLogZoom,
        driftX,
        driftY,
        driftTX,
        driftTY,
    ])

    // ---- Input: drag, wheel (zoom), mouse-parallax drift -------------------

    useEffect(() => {
        const el = containerRef.current
        if (!el || isStatic) return

        let dragging = false
        let lastPX = 0
        let lastPY = 0
        let lastT = 0
        let pid: number | null = null
        let startX = 0, startY = 0, moved = false, clickHref = ""
        const touches = new Map<number, {x: number, y: number}>()
        let pinchDistance = 0
        const distance = () => { const p = Array.from(touches.values()); return p.length >= 2 ? Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y) : 0 }

        const onDown = (e: PointerEvent) => {
            if (e.button !== 0 && e.pointerType === "mouse") return
            if (e.pointerType !== "mouse" && !touchEnabled) return
            if (e.pointerType === "touch") {
                touches.set(e.pointerId, {x: e.clientX, y: e.clientY})
                if (touches.size >= 2) {
                    pinchDistance = distance(); dragging = false; pid = null; clickHref = ""; moved = true
                    try { el.setPointerCapture(e.pointerId) } catch {}
                    return
                }
            }
            if (dragging) return
            startX = e.clientX; startY = e.clientY; moved = false
            clickHref = (e.target as HTMLElement).closest<HTMLElement>("[data-href]")?.dataset.href || ""
            dragging = true
            pid = e.pointerId
            lastPX = e.clientX
            lastPY = e.clientY
            lastT = e.timeStamp
            try {
                el.setPointerCapture(e.pointerId)
            } catch {}
            el.style.cursor = "grabbing"
        }

        const onMove = (e: PointerEvent) => {
            if (e.pointerType === "touch" && touches.has(e.pointerId)) {
                touches.set(e.pointerId, {x: e.clientX, y: e.clientY})
                if (touches.size >= 2 && pinchDistance > 0) {
                    const next = distance()
                    if (next > 0) targetLogZoom.set(targetLogZoom.get() + Math.log2(next / pinchDistance))
                    pinchDistance = next; velLogZoom.set(0); return
                }
            }
            const rect = el.getBoundingClientRect()
            const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1
            const ny = ((e.clientY - rect.top) / rect.height) * 2 - 1
            driftTX.set(Math.max(-1, Math.min(1, nx)))
            driftTY.set(Math.max(-1, Math.min(1, ny)))

            if (!dragging || e.pointerId !== pid) return

            const dpx = e.clientX - lastPX
            const dpy = e.clientY - lastPY
            if (Math.hypot(e.clientX - startX, e.clientY - startY) > 7) moved = true

            // Convert pixel delta to world units using the ACTUAL on-screen
            // scale, not the absolute zoom. Tiles project at layerScale = 2^frac
            // (octave-relative, bounded), so dividing by 2^logZoom made the
            // world delta explode when zoomed out. Use the alpha-weighted
            // on-screen scale (≈1, continuous across octave wraps) so drag
            // tracks the finger 1:1 at any zoom with no speed jump.
            const lz = logZoom.get()
            const frac = lz - Math.floor(lz)
            const effScale =
                (1 - frac) * Math.pow(2, frac) + frac * Math.pow(2, frac - 1)
            const dWorldX = (-dpx / (PX_PER_UNIT * effScale)) * safeDragSpeed
            const dWorldY = (-dpy / (PX_PER_UNIT * effScale)) * safeDragSpeed
            targetX.set(targetX.get() + dWorldX)
            targetY.set(targetY.get() + dWorldY)

            const dt = Math.max(1, e.timeStamp - lastT)
            const k = 16 / dt
            velX.set(dWorldX * k)
            velY.set(dWorldY * k)

            lastPX = e.clientX
            lastPY = e.clientY
            lastT = e.timeStamp
        }

        const onUp = (e: PointerEvent) => {
            if (e.pointerType === "touch" && touches.has(e.pointerId)) {
                touches.delete(e.pointerId)
                if (pinchDistance > 0) {
                    try { el.releasePointerCapture(e.pointerId) } catch {}
                    if (touches.size < 2) pinchDistance = 0
                    dragging = false; pid = null; clickHref = ""; el.style.cursor = "grab"; return
                }
            }
            if (!dragging || e.pointerId !== pid) return
            dragging = false
            pid = null
            try {
                el.releasePointerCapture(e.pointerId)
            } catch {}
            el.style.cursor = "grab"
            if (!moved && clickHref && e.type === "pointerup") {
                sessionStorage.setItem("ac-gallery-v5", JSON.stringify({x: targetX.get(), y: targetY.get(), zoom: targetLogZoom.get()}))
                window.location.assign(clickHref)
            }
            clickHref = ""
        }

        const onCancel = (e: PointerEvent) => onUp(e)

        const onWheel = (e: WheelEvent) => {
            e.preventDefault()
            let delta = e.deltaY
            if (e.deltaMode === 1) delta *= 16
            else if (e.deltaMode === 2) delta *= 400
            const step = -delta * 0.0015 * safeDragSpeed
            if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) targetLogZoom.set(targetLogZoom.get() + step * 4)
            else velLogZoom.set(velLogZoom.get() + step)
        }

        const onLeave = () => {
            driftTX.set(0)
            driftTY.set(0)
        }

        el.addEventListener("pointerdown", onDown)
        el.addEventListener("pointermove", onMove)
        el.addEventListener("pointerup", onUp)
        el.addEventListener("pointercancel", onCancel)
        el.addEventListener("wheel", onWheel, { passive: false })
        const onKey=(e:KeyboardEvent)=>{if(e.target!==el)return;const step=35;if(e.key==="ArrowLeft")targetX.set(targetX.get()-step);else if(e.key==="ArrowRight")targetX.set(targetX.get()+step);else if(e.key==="ArrowUp")targetY.set(targetY.get()-step);else if(e.key==="ArrowDown")targetY.set(targetY.get()+step);else if(e.key==="+"||e.key==="=")targetLogZoom.set(targetLogZoom.get()+.35);else if(e.key==="-")targetLogZoom.set(targetLogZoom.get()-.35);else return;e.preventDefault()}
        el.addEventListener("keydown",onKey)
        el.addEventListener("pointerleave", onLeave)

        el.style.cursor = "grab"

        return () => {
            el.removeEventListener("pointerdown", onDown)
            el.removeEventListener("pointermove", onMove)
            el.removeEventListener("pointerup", onUp)
            el.removeEventListener("pointercancel", onCancel)
            el.removeEventListener("wheel", onWheel)
            el.removeEventListener("keydown", onKey)
            el.removeEventListener("pointerleave", onLeave)
        }
    }, [
        isStatic,
        safeDragSpeed,
        touchEnabled,
        targetX,
        targetY,
        velX,
        velY,
        velLogZoom,
        logZoom,
        driftTX,
        driftTY,
    ])

    // ---- Render -------------------------------------------------------------

    const resolveDim = (
        v: string | number | undefined,
        fallback: string
    ): string => {
        if (v == null) return fallback
        if (typeof v === "number") return `${v}px`
        return v
    }

    const wrapperStyle: React.CSSProperties = {
        position: "relative",
        isolation: "isolate",
        width: resolveDim(width, "100%"),
        height: resolveDim(height, "100%"),
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        backgroundColor,
        touchAction: touchEnabled ? "none" : "pan-y",
        userSelect: "none",
        cursor: "grab",
        ...style,
    }

    const sceneStyle: React.CSSProperties = {
        position: "absolute",
        inset: 0,
    }

    return (
        <div ref={containerRef} className={className} style={wrapperStyle} role="region" aria-label="Project canvas" tabIndex={0}>
            <div ref={sceneRef} style={sceneStyle} />
        </div>
    )
}

const COMPONENT_DEFAULTS = {
    width: "100%",
    height: "100%",
    className: "",
    images: DEFAULT_IMAGES,
    density: 5,
    imageWidth: 150,
    imageHeight: 150,
    rounded: 3,
    dragSpeed: 20,
    driftAmount: 20,
    friction: 10,
    backgroundColor: "#000000",
}