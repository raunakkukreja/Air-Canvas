// export.js — PNG save, OBJ export, standalone Three.js viewer (port of export.py)
import { W, H } from './config.js';

const stamp = () => new Date().toISOString().replace(/[-:]/g, '').replace('T', '_').slice(0, 15);
const hex = (c) => '#' + c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');

export function download(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const images = {};
const loadImg = (src) =>
  (images[src] ??= new Promise((ok, fail) => {
    const img = new Image();
    img.onload = () => ok(img);
    img.onerror = fail;
    img.src = src;
  }));

/** Composite the 2D layers onto a background and download a PNG. bg: raw|white|brick|white_brick */
export async function saveCanvas2D(canvas2d, bg) {
  const out = document.createElement('canvas');
  out.width = W;
  out.height = H;
  const ctx = out.getContext('2d');
  if (bg === 'brick' || bg === 'white_brick') ctx.drawImage(await loadImg(`assets/${bg}.jpg`), 0, 0, W, H);
  else {
    ctx.fillStyle = bg === 'white' ? '#fff' : '#000';
    ctx.fillRect(0, 0, W, H);
  }
  composite2D(ctx, canvas2d);
  const name = `graffiti_${bg}_${stamp()}.png`;
  out.toBlob((b) => download(b, name));
  return name;
}

/** Ink layers + neon bloom, shared by the live view and PNG export. */
export function composite2D(ctx, canvas2d) {
  ctx.drawImage(canvas2d.canvas, 0, 0);
  ctx.drawImage(canvas2d.glowCanvas, 0, 0);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.filter = 'blur(10px)';
  ctx.drawImage(canvas2d.glowCanvas, 0, 0);
  ctx.restore();
}

/** OBJ with `l` (polyline) elements for strokes and `p` (points) for spray. Y flipped to up. */
export function exportObj(strokes) {
  const lines = ['# Air Canvas 3D Export'];
  let vi = 1;
  for (const s of strokes) {
    for (const p of s.points) lines.push(`v ${p[0].toFixed(4)} ${(-p[1]).toFixed(4)} ${p[2].toFixed(4)}`);
    lines.push(`${s.spray ? 'p' : 'l'} ${s.points.map((_, i) => vi + i).join(' ')}`);
    vi += s.points.length;
  }
  return lines.join('\n') + '\n';
}

/** Standalone HTML page that orbits the drawing with Three.js. bg: black|white */
export function viewerHtml(strokes, bg = 'black') {
  const dark = bg === 'black';
  const calls = strokes.map((s) => {
    let col = hex(s.color);
    // keep near-black ink visible on black and near-white ink visible on white
    if (dark && s.color.every((c) => c < 30)) col = '#ffffff';
    else if (!dark && s.color.every((c) => c > 220)) col = '#000000';
    const coords = s.points.map((p) => `${p[0].toFixed(3)},${(-p[1]).toFixed(3)},${p[2].toFixed(3)}`).join(',');
    return `${s.spray ? 'addPoints' : 'addLine'}([${coords}],"${col}",${s.thickness});`;
  });
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Air Canvas 3D Viewer</title>
<style>body{margin:0;background:${dark ? '#111' : '#fff'};overflow:hidden}canvas{display:block}</style>
</head><body>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const scene = new THREE.Scene();
scene.background = new THREE.Color(${dark ? '0x111111' : '0xffffff'});
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 1000);
camera.position.set(0, 2, 5);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.GridHelper(10, 20, ${dark ? '0x555555, 0x333333' : '0xaaaaaa, 0xdddddd'}));
scene.add(new THREE.AxesHelper(3));
const pts = (c) => { const a = []; for (let i = 0; i < c.length; i += 3) a.push(new THREE.Vector3(c[i], c[i + 1], c[i + 2])); return a; };
function addLine(c, color) {
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts(c)), new THREE.LineBasicMaterial({ color })));
}
function addPoints(c, color, size) {
  scene.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(pts(c)),
    new THREE.PointsMaterial({ color, size: size * 0.015, sizeAttenuation: true })));
}
${calls.join('\n')}
(function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
</script></body></html>`;
}

export const exportName = (ext, bg = '') => `air_canvas_3d${bg ? '_' + bg : ''}_${stamp()}.${ext}`;
