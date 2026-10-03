// gestures.js — landmark analysis, gesture classification, smoothing (port of hand_tracker.py)
import { FINGER_UP_THRESH, THUMB_DISTANCE_THRESH, SMOOTH_FACTOR, DEPTH_SCALE } from './config.js';

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Finger state + raw gesture for 21 normalized landmarks ({x, y, z}). */
export function analyze(lm) {
  const hs = Math.max(Math.abs(lm[9].y - lm[0].y), 0.05);
  const up = (pip, tip) => (lm[pip].y - lm[tip].y) / hs > FINGER_UP_THRESH;
  const curl = (pip, tip) => lm[tip].y > lm[pip].y;
  const f = {
    indexUp: up(6, 8), middleUp: up(10, 12), ringUp: up(14, 16), pinkyUp: up(18, 20),
    indexCurl: curl(6, 8), middleCurl: curl(10, 12), ringCurl: curl(14, 16), pinkyCurl: curl(18, 20),
  };
  const tt = lm[4], tb = lm[2];
  const mostlyCurled = [f.indexCurl, f.middleCurl, f.ringCurl, f.pinkyCurl].filter(Boolean).length >= 3;
  const dThumb = dist(tt, lm[5]) / hs;
  f.thumbUp = mostlyCurled && dThumb > THUMB_DISTANCE_THRESH && tb.y > tt.y;
  f.thumbDown = mostlyCurled && dThumb > THUMB_DISTANCE_THRESH && tt.y > tb.y;
  f.gesture = classify(f, lm, dThumb);
  return f;
}

function classify(f, lm, dThumb) {
  const allUp = f.indexUp && f.middleUp && f.ringUp && f.pinkyUp;
  const allCurl = f.indexCurl && f.middleCurl && f.ringCurl && f.pinkyCurl;

  if (allUp && !allCurl && dThumb > THUMB_DISTANCE_THRESH) return 'five_fingers_up';
  if (allUp) return dThumb < THUMB_DISTANCE_THRESH || lm[4].y >= lm[5].y ? 'rotate_3d' : 'open_palm';
  if (f.indexUp && f.pinkyUp && !f.middleUp && !f.ringUp && f.middleCurl && f.ringCurl) return 'rock_sign';
  if (f.indexUp && f.middleUp && f.ringUp && !f.pinkyUp && f.pinkyCurl) return 'erase';
  if (f.indexUp && f.middleUp && !f.ringUp && !f.pinkyUp && f.ringCurl && f.pinkyCurl) return 'two_finger';
  if (f.indexUp && !f.middleUp && !f.ringUp && !f.pinkyUp && f.middleCurl && f.ringCurl && f.pinkyCurl) return 'draw';
  if (f.pinkyUp && !f.indexUp && !f.middleUp && !f.ringUp && f.indexCurl && f.middleCurl && f.ringCurl) return 'pinky_only';
  if (f.middleUp && !f.indexUp && !f.ringUp && !f.pinkyUp && f.indexCurl && f.ringCurl && f.pinkyCurl) return 'middle_only';
  if (allCurl) return f.thumbUp ? 'thumb_up' : f.thumbDown ? 'thumb_down' : 'fist';
  if (dist(lm[4], lm[8]) < 0.05 && !f.middleUp && !f.ringUp && !f.pinkyUp) return 'pinch';
  return 'none';
}

/** Stateful per-hand smoothing and 5-frame gesture voting. */
export class Tracker {
  constructor() {
    this.smooth = {};
    this.history = { Left: [], Right: [] };
  }

  /**
   * hands: [{label, landmarks}] with landmarks already mirrored (selfie view).
   * toPx(x, y) maps normalized coords to canvas pixels.
   */
  process(hands, toPx) {
    return hands.map(({ label, landmarks: lm }) => {
      const f = analyze(lm);
      const tip = f.gesture === 'middle_only' ? lm[12] : lm[8];
      const [x, y] = toPx(tip.x, tip.y);
      const [ox, oy, oz] = this.smooth[label] ?? [x, y, tip.z];
      const k = SMOOTH_FACTOR;
      const sx = Math.round((1 - k) * ox + k * x);
      const sy = Math.round((1 - k) * oy + k * y);
      const sz = (1 - k) * oz + k * tip.z;
      this.smooth[label] = [sx, sy, sz];

      const hist = this.history[label];
      hist.push(f.gesture);
      if (hist.length > 5) hist.shift();
      const counts = {};
      for (const g of hist) counts[g] = (counts[g] ?? 0) + 1;
      const gesture = Object.keys(counts).reduce((a, b) => (counts[b] > counts[a] ? b : a));

      return { ...f, label, landmarks: lm, gesture, rawGesture: f.gesture, z: tip.z, sx, sy, sz,
               depth: -sz * DEPTH_SCALE };
    });
  }
}
