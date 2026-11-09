import { build } from 'esbuild';
await build({ entryPoints:['frontend/main.tsx'], bundle:true, minify:true, sourcemap:false, target:['es2020'], outfile:'static/components.js', define:{'process.env.NODE_ENV':'"production"'} });
