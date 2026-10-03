// app.js — camera, hand tracking, gesture → action loop (port of main.py)
import { FilesetResolver, HandLandmarker } from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/vision_bundle.mjs';
import { W, H, MODE_2D, MODE_3D, COLORS_LIST, TOOLBAR_H, MIN_BRUSH_SIZE, MAX_BRUSH_SIZE, ERASER_SIZE,
         SPRAY_TOGGLE_HOLD, UNDO_REDO_HOLD, CLEAR_HOLD_TIME, THUMB_UP_HOLD, MODE_SWITCH_HOLD,
         SYMMETRY_TOGGLE_HOLD, MAX_HANDS, MIN_DETECTION_CONF, MIN_TRACKING_CONF } from './config.js';
import { Tracker } from './gestures.js';
import { Canvas2D } from './canvas2d.js';
import { Scene3D } from './scene3d.js';
import { put, drawToolbar, drawHoldBar, FPSCounter, SaveMenu, ModeSelector, ParticleSystem,
         depthToPressure, drawHand } from './ui.js';
import { saveCanvas2D, composite2D, exportObj, viewerHtml, exportName, download } from './export.js';

const $ = (id) => document.getElementById(id);
const video = $('video');
const out = $('stage');
out.width = W;
out.height = H;
const ctx = out.getContext('2d');

// mirrored camera frame: fed to the detector and sampled by the color picker
const cam = document.createElement('canvas');
cam.width = W;
cam.height = H;
const camCtx = cam.getContext('2d', { willReadFrequently: true });
const frozen = document.createElement('canvas');
frozen.width = W;
frozen.height = H;
let isFrozen = false;

const tracker = new Tracker();
const canvas2d = new Canvas2D();
const scene3d = new Scene3D(W, H);
const particles = new ParticleSystem();
const fps = new FPSCounter();
const saveMenu = new SaveMenu();
const modeSel = new ModeSelector();

let mode = MODE_2D;
let glowOn = false;
let landmarker;

const now = () => performance.now() / 1000;
const hold = { spray: 0, clear: 0, save: 0, fist: 0, rock: 0, undo: 0, redo: 0 };
let undoTime = 0, redoTime = 0, showUndo = 0;
let feedback = { until: 0, text: '' };
const lastGesture = {};
const prevErase3D = {};

/** Close the hand's open stroke/rotation so the next gesture starts fresh. */
function endStroke(label) {
  canvas2d.finishStroke(label, glowOn);
  canvas2d.prev[label] = null;
  scene3d.finishStroke(label);
  scene3d.stopRotate();
  prevErase3D[label] = null;
}

/** Hold-to-trigger timer: returns seconds held so far (timer starts on first call). */
const held = (key) => {
  if (!hold[key]) hold[key] = now();
  return now() - hold[key];
};

function pickColor(sx, sy) {
  const d = camCtx.getImageData(Math.max(0, sx - 3), Math.max(0, sy - 3), 6, 6).data;
  const c = [0, 0, 0];
  for (let i = 0; i < d.length; i += 4) for (let k = 0; k < 3; k++) c[k] += d[i + k];
  canvas2d.brushColor = c.map((v) => Math.round(v / (d.length / 4)));
  ctx.beginPath();
  ctx.arc(sx, sy - 25, 15, 0, Math.PI * 2);
  ctx.fillStyle = `rgb(${canvas2d.brushColor})`;
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.stroke();
  put(ctx, 'PICK', sx - 18, sy - 45, 0.4);
}

function toolbarSelect(sx) {
  for (const [, col, cx] of COLORS_LIST) if (Math.abs(sx - cx) < 25) canvas2d.brushColor = col;
  if (sx > 420 && sx < 540) canvas2d.brushMode = true;
}

function brushSlider(sx, sy, g) {
  if (!canvas2d.brushMode) return;
  if (sx > 550 && sx < 770 && sy < TOOLBAR_H) {
    const ratio = (sx - 550) / 220;
    canvas2d.brushSize = Math.max(MIN_BRUSH_SIZE, Math.min(MAX_BRUSH_SIZE, Math.round(2 + ratio * 28)));
  }
  if (['draw', 'erase', 'fist'].includes(g)) canvas2d.brushMode = false;
}

function sprayRadius(hd) {
  const palm = Math.abs((hd.landmarks[9].y - hd.landmarks[0].y) * H);
  return Math.max(8, Math.min(80, Math.round(180 - palm)));
}

function handleHand(hd, flags) {
  const { sx, sy, gesture: g, label } = hd;

  if (g === 'thumb_down') return (flags.thumbDown = true);
  if (g === 'thumb_up') return (flags.thumbUp = true);

  if (g === 'fist') {
    const t = held('fist');
    put(ctx, `MODE: ${Math.max(0, MODE_SWITCH_HOLD - t).toFixed(1)}`, sx - 40, sy - 30, 0.6, '#fff');
    if (t >= MODE_SWITCH_HOLD) {
      modeSel.open();
      hold.fist = 0;
    }
    return;
  }
  if (g === 'rock_sign' && mode === MODE_2D) {
    const t = held('rock');
    put(ctx, `SYMMETRY ${canvas2d.symmetry ? 'OFF' : 'ON'}: ${Math.max(0, SYMMETRY_TOGGLE_HOLD - t).toFixed(1)}`,
      sx - 60, sy - 30, 0.5, '#00c8c8');
    if (t >= SYMMETRY_TOGGLE_HOLD) {
      canvas2d.symmetry = !canvas2d.symmetry;
      hold.rock = 0;
    }
    return;
  }
  if (g === 'pinky_only') {
    const t = held('spray');
    put(ctx, `${canvas2d.sprayOn ? 'Turn OFF' : 'Turn ON'}: ${Math.max(0, SPRAY_TOGGLE_HOLD - t).toFixed(1)}s`,
      W - 330, 90, 0.5, '#fff');
    if (t >= SPRAY_TOGGLE_HOLD) {
      canvas2d.sprayOn = !canvas2d.sprayOn;
      hold.spray = 0;
    }
    return;
  }
  if (g === 'two_finger') flags[label === 'Right' ? 'undo' : 'redo'] = true;

  // cursor
  ctx.beginPath();
  ctx.arc(sx, sy, 10, 0, Math.PI * 2);
  ctx.fillStyle = `rgb(${canvas2d.brushColor})`;
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1;
  ctx.stroke();

  if (mode === MODE_3D) return handle3D(hd);

  // ── 2D ──
  if (['five_fingers_up', 'open_palm', 'rotate_3d'].includes(g)) {
    if (sy < TOOLBAR_H) toolbarSelect(sx);
  } else if (g === 'middle_only' && sy > TOOLBAR_H) pickColor(sx, sy);
  brushSlider(sx, sy, g);

  if (canvas2d.sprayOn && g === 'draw') {
    const r = sprayRadius(hd);
    put(ctx, `SPRAY r:${r}`, W - 330, 90, 0.5, '#fff');
    canvas2d.sprayPaint(label, sx, sy, r, Math.max(20, Math.min(100, r * 2)), canvas2d.brushColor, glowOn);
    particles.emit(sx, sy, canvas2d.brushColor, 2);
  } else if (g === 'draw' || g === 'erase') {
    const erase = g === 'erase';
    const p = canvas2d.prev[label];
    if (p) canvas2d.drawLine(label, p, [sx, sy], erase ? null : canvas2d.brushColor,
      erase ? ERASER_SIZE : depthToPressure(hd.z, canvas2d.brushSize), glowOn);
    canvas2d.prev[label] = [sx, sy];
  }
}

function handle3D(hd) {
  const { sx, sy, gesture: g, label } = hd;
  if (sy < TOOLBAR_H) {
    scene3d.stopRotate();
    if (['five_fingers_up', 'open_palm', 'middle_only'].includes(g)) toolbarSelect(sx);
    brushSlider(sx, sy, g);
    return;
  }
  if (g === 'middle_only') return pickColor(sx, sy);
  if (g === 'rotate_3d') {
    if (sy < 80) return scene3d.stopRotate();
    if (!scene3d.rotAnchor) scene3d.startRotate(sx, sy);
    scene3d.updateRotate(sx, sy);
    return put(ctx, 'ROTATING', sx - 40, sy - 30, 0.5, '#00c8c8');
  }
  if (g === 'pinch') {
    const zoomIn = label === 'Right';
    scene3d.adjustZoom(zoomIn ? 0.015 : -0.015);
    return put(ctx, zoomIn ? 'ZOOM IN +' : 'ZOOM OUT -', sx - 40, sy - 30, 0.5, zoomIn ? '#00c800' : '#ff5050');
  }
  if (g === 'draw') {
    if (canvas2d.sprayOn) {
      const r = sprayRadius(hd);
      scene3d.sprayPaint(label, sx, sy, hd.depth, r, Math.max(20, Math.min(100, r * 2)), canvas2d.brushColor, 4);
      particles.emit(sx, sy, canvas2d.brushColor, 2);
    } else {
      if (!scene3d.current[label]) scene3d.startStroke(label, canvas2d.brushColor, canvas2d.brushSize);
      scene3d.addPoint(label, sx, sy, hd.depth);
      put(ctx, `Depth: ${Math.round(Math.max(0, Math.min(100, 50 + hd.sz * 200)))}%`, sx + 15, sy - 10, 0.4, '#ddd');
    }
  } else if (g === 'erase') {
    scene3d.eraseAt(sx, sy, prevErase3D[label]);
    prevErase3D[label] = [sx, sy];
    put(ctx, '3D ERASING', sx + 15, sy - 10, 0.4, '#ff5050');
  }
}

/** Hold a gesture for `total` seconds to fire `action` once; shows a progress bar. */
function holdAction(active, key, label, total, color, action) {
  if (!active) return (hold[key] = 0);
  const t = held(key);
  drawHoldBar(ctx, label, t, total, color);
  if (t >= total) {
    hold[key] = 0;
    action();
  }
}

function frame() {
  requestAnimationFrame(frame);
  if ($('viewer').open || video.readyState < 2) return;
  fps.tick();

  // camera → mirrored, cover-fitted
  const s = Math.max(W / video.videoWidth, H / video.videoHeight);
  const vw = video.videoWidth * s, vh = video.videoHeight * s;
  camCtx.save();
  camCtx.translate(W, 0);
  camCtx.scale(-1, 1);
  camCtx.drawImage(video, (W - vw) / 2, (H - vh) / 2, vw, vh);
  camCtx.restore();

  const res = landmarker.detectForVideo(cam, performance.now());
  const hands = tracker.process(
    res.landmarks.map((lm, i) => ({ label: res.handedness[i][0].categoryName, landmarks: lm })),
    (x, y) => [x * W, y * H],
  );

  // background, skeletons, ink
  ctx.drawImage(isFrozen ? frozen : cam, 0, 0);
  for (const hd of hands) drawHand(ctx, hd.landmarks.map((p) => [p.x * W, p.y * H]));
  if (mode === MODE_2D) composite2D(ctx, canvas2d);
  else scene3d.render(ctx);

  // gestures
  for (const label of Object.keys(lastGesture)) {
    if (!hands.some((h) => h.label === label)) {
      endStroke(label);
      delete lastGesture[label];
    }
  }
  const flags = {};
  let menuFinger = null;
  for (const hd of hands) {
    if (hd.gesture !== lastGesture[hd.label]) endStroke(hd.label);
    lastGesture[hd.label] = hd.gesture;
    if (saveMenu.active || modeSel.active) {
      if (hd.indexUp) menuFinger = [hd.sx, hd.sy];
      continue;
    }
    handleHand(hd, flags);
  }
  const seen = new Set(hands.map((h) => h.gesture));
  if (!seen.has('fist')) hold.fist = 0;
  if (!seen.has('rock_sign')) hold.rock = 0;
  if (!seen.has('pinky_only')) hold.spray = 0;

  const menuOpen = saveMenu.active || modeSel.active;
  holdAction(flags.thumbUp && !menuOpen, 'save', 'SAVE', THUMB_UP_HOLD, '#00b400', () => saveMenu.open());
  holdAction(flags.thumbDown && !menuOpen, 'clear', 'CLEAR ALL', CLEAR_HOLD_TIME, '#dc0000',
    () => (mode === MODE_2D ? canvas2d.clear() : scene3d.clear()));

  const target = mode === MODE_2D ? canvas2d : scene3d;
  if (flags.undo && !flags.thumbDown) {
    const t = held('undo');
    put(ctx, `UNDO ${Math.max(0, UNDO_REDO_HOLD - t).toFixed(1)}`, 40, 110, 0.8, '#ff5050');
    if (t >= UNDO_REDO_HOLD && now() - undoTime > UNDO_REDO_HOLD + 0.1) {
      undoTime = now();
      hold.undo = 0;
      showUndo = now() + 1;
      target.undo();
    }
  } else hold.undo = 0;
  if (flags.redo && !flags.thumbDown) {
    const t = held('redo');
    put(ctx, `REDO ${Math.max(0, UNDO_REDO_HOLD - t).toFixed(1)}`, 40, 140, 0.8, '#00c800');
    if (t >= UNDO_REDO_HOLD && now() - redoTime > UNDO_REDO_HOLD + 0.1) {
      redoTime = now();
      hold.redo = 0;
      target.redo();
    }
  } else hold.redo = 0;
  if (now() < showUndo) put(ctx, 'UNDO!', 40, 110, 0.8, '#ff5050');

  if (saveMenu.active) {
    const choice = saveMenu.drawAndCheck(ctx, menuFinger, mode);
    if (choice) save(choice);
  }
  particles.updateAndDraw(ctx);
  drawToolbar(ctx, { ...canvas2d, mode, glowOn });
  fps.draw(ctx);
  if (modeSel.active) mode = modeSel.drawAndCheck(ctx, menuFinger) ?? mode;
  if (now() < feedback.until) {
    ctx.textAlign = 'center';
    put(ctx, feedback.text, W / 2, H / 2, 0.9, '#00dc00');
    ctx.textAlign = 'left';
  }
}

async function save(choice) {
  if (mode === MODE_2D) {
    feedback = { until: now() + 2.5, text: `SAVED: ${await saveCanvas2D(canvas2d, choice)}` };
    return;
  }
  $('viewer-frame').srcdoc = viewerHtml(scene3d.strokes, choice);
  $('viewer').dataset.bg = choice;
  $('viewer').showModal();
}

// ── viewer dialog ───────────────────────────────────────────
$('dl-html').onclick = () => {
  const bg = $('viewer').dataset.bg;
  download(new Blob([viewerHtml(scene3d.strokes, bg)], { type: 'text/html' }), exportName('html', bg));
};
$('dl-obj').onclick = () => download(new Blob([exportObj(scene3d.strokes)], { type: 'text/plain' }), exportName('obj'));
$('viewer-close').onclick = () => $('viewer').close();

// ── keyboard (same keys as the desktop app) ─────────────────
addEventListener('keydown', (e) => {
  if (e.key === 'g') glowOn = !glowOn;
  else if (e.key === 's') canvas2d.symmetry = !canvas2d.symmetry;
  else if (e.key === 'f') {
    isFrozen = !isFrozen;
    if (isFrozen) frozen.getContext('2d').drawImage(cam, 0, 0);
  } else if (e.key === 'h') $('help').toggleAttribute('open');
});

// ── startup ─────────────────────────────────────────────────
async function createLandmarker(delegate) {
  const files = await FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm');
  return HandLandmarker.createFromOptions(files, {
    baseOptions: {
      modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
      delegate,
    },
    runningMode: 'VIDEO',
    numHands: MAX_HANDS,
    minHandDetectionConfidence: MIN_DETECTION_CONF,
    minTrackingConfidence: MIN_TRACKING_CONF,
  });
}

$('start').onclick = async () => {
  const status = $('status');
  $('start').disabled = true;
  try {
    status.textContent = 'Requesting camera…';
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
    });
    await video.play();
    status.textContent = 'Loading hand-tracking model…';
    landmarker = await createLandmarker('GPU').catch(() => createLandmarker('CPU'));
    $('intro').hidden = true;
    requestAnimationFrame(frame);
  } catch (err) {
    status.textContent = err.name === 'NotAllowedError'
      ? 'Camera access was blocked. Allow it in the address bar and try again.'
      : `Could not start: ${err.message}`;
    $('start').disabled = false;
  }
};
