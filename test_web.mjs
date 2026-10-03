// test_web.mjs — headless checks for the browser port (gestures, 3D math, exports)
// Run: node test_web.mjs
import assert from 'node:assert/strict';
import { analyze, Tracker } from './web/js/gestures.js';
import { Scene3D } from './web/js/scene3d.js';
import { exportObj, viewerHtml } from './web/js/export.js';

// Same synthetic hand as test_core.py: wrist y=.8, middle MCP y=.6 → hand scale .2
function makeHand(up = [], thumb = 'in') {
  const pts = Array.from({ length: 21 }, () => [0.5, 0.5]);
  pts[0] = [0.5, 0.8]; pts[9] = [0.5, 0.6]; pts[5] = [0.45, 0.6];
  const fingers = { index: [6, 8, 0.45], middle: [10, 12, 0.5], ring: [14, 16, 0.55], pinky: [18, 20, 0.6] };
  for (const [name, [pip, tip, x]] of Object.entries(fingers)) {
    pts[pip] = [x, 0.55];
    pts[tip] = [x, up.includes(name) ? 0.4 : 0.6];
  }
  pts[2] = [0.38, 0.65];
  pts[4] = { in: [0.45, 0.62], up: [0.3, 0.55], down: [0.3, 0.75] }[thumb];
  return pts.map(([x, y]) => ({ x, y, z: 0 }));
}

const all = ['index', 'middle', 'ring', 'pinky'];
const cases = {
  draw: makeHand(['index']),
  two_finger: makeHand(['index', 'middle']),
  erase: makeHand(['index', 'middle', 'ring']),
  rock_sign: makeHand(['index', 'pinky']),
  pinky_only: makeHand(['pinky']),
  middle_only: makeHand(['middle']),
  five_fingers_up: makeHand(all, 'up'),
  rotate_3d: makeHand(all, 'in'),
  fist: makeHand(),
  thumb_up: makeHand([], 'up'),
  thumb_down: makeHand([], 'down'),
};
for (const [want, lm] of Object.entries(cases)) assert.equal(analyze(lm).gesture, want, want);

// voting: one stray frame doesn't flip a held gesture; smoothing moves toward the new position
const t = new Tracker();
const px = (x, y) => [x * 1000, y * 1000];
for (let i = 0; i < 4; i++) t.process([{ label: 'Right', landmarks: cases.draw }], px);
assert.equal(t.process([{ label: 'Right', landmarks: cases.fist }], px)[0].gesture, 'draw');

// 3D: parity with Python Scene3D (values from scene_3d.py, same rotation/zoom)
const s = new Scene3D(1280, 720);
s.rotation = [20, -35, 10];
s.zoom = 1.4;
const [[x, y], z] = s.project([0.7, -0.4, 1.2]);
assert.ok(Math.abs(x - 677) < 1 && Math.abs(y - 154) < 1 && Math.abs(z - 4.213138) < 1e-5, `${x},${y},${z}`);
const w = s.unproject(100, 200, -0.3);
[-1.2770986, 0.0360609, 0.5487626].forEach((v, i) => assert.ok(Math.abs(w[i] - v) < 1e-6, `unproject ${i}`));

// stroke → erase middle → split; undo/redo
s.startStroke('Right', [255, 0, 0], 4);
for (const [sx, sy] of [[100, 200], [120, 200], [320, 240], [500, 90], [520, 90]]) s.addPoint('Right', sx, sy, -0.3);
s.finishStroke('Right');
assert.ok(s.eraseAt(320, 240, null, 10));
assert.deepEqual(s.strokes.map((st) => st.points.length), [2, 2]);
assert.ok(s.undo() && s.strokes.length === 1 && s.redo() && s.strokes.length === 2);

// exports
const strokes = [{ points: [[0, 0, 0], [1, 1, 1]], color: [255, 0, 0], thickness: 3 },
                 { points: [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5], [0.5, 0.5, 0.5]], color: [20, 20, 20], thickness: 4, spray: true }];
const obj = exportObj(strokes).split('\n');
assert.equal(obj.filter((l) => l.startsWith('v ')).length, 5);
assert.ok(obj.includes('l 1 2') && obj.includes('p 3 4 5') && obj.includes('v 1.0000 -1.0000 1.0000'));
const html = viewerHtml(strokes, 'black');
assert.ok(html.includes('"#ff0000"') && html.includes('"#ffffff"'), 'red stays red, near-black → white on black');
assert.ok(viewerHtml(strokes, 'white').includes('"#141414"'));

console.log('ok test_web: gestures, voting, 3D parity, erase/undo, exports');
