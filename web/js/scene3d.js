// scene3d.js — 3D drawing engine: strokes, rotation, projection (port of scene_3d.py)
// Points are [x, y, z] in world space. Math is DOM-free so it can be tested in Node.
import { SCENE_FOV, SCENE_Z_OFFSET, ROT_SPEED, MIN_ZOOM, MAX_ZOOM, rgb } from './config.js';

const mul = (R, p) => [
  R[0][0] * p[0] + R[0][1] * p[1] + R[0][2] * p[2],
  R[1][0] * p[0] + R[1][1] * p[1] + R[1][2] * p[2],
  R[2][0] * p[0] + R[2][1] * p[1] + R[2][2] * p[2],
];
const mulT = (R, p) => [
  R[0][0] * p[0] + R[1][0] * p[1] + R[2][0] * p[2],
  R[0][1] * p[0] + R[1][1] * p[1] + R[2][1] * p[2],
  R[0][2] * p[0] + R[1][2] * p[1] + R[2][2] * p[2],
];

/** Distance from point p to segment a-b (b may be null → point distance). */
function segDist(px, py, ax, ay, b) {
  if (!b) return Math.hypot(px - ax, py - ay);
  const abx = b[0] - ax, aby = b[1] - ay, ab2 = abx * abx + aby * aby;
  if (ab2 < 1e-6) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / ab2));
  return Math.hypot(px - (ax + t * abx), py - (ay + t * aby));
}

export class Scene3D {
  constructor(w, h) {
    this.w = w;
    this.h = h;
    this.strokes = []; // [{points, color, thickness, spray?}]
    this.redoStack = [];
    this.current = { Left: null, Right: null };
    this.rotation = [0, 0, 0]; // pitch, yaw, roll (degrees)
    this.zoom = 1;
    this.origin = [w / 2, h / 2];
    this.rotAnchor = null;
    this.rotSnap = null;
  }

  rotMat() {
    const [rx, ry, rz] = this.rotation.map((d) => (d * Math.PI) / 180);
    const [cx, sx, cy, sy, cz, sz] = [Math.cos(rx), Math.sin(rx), Math.cos(ry), Math.sin(ry), Math.cos(rz), Math.sin(rz)];
    // Rz · Ry · Rx
    return [
      [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
      [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
      [-sy, cy * sx, cy * cx],
    ];
  }

  /** world point → [[sx, sy], depth] */
  project(pt, R = this.rotMat()) {
    const p = mul(R, pt);
    const fov = SCENE_FOV * this.zoom;
    let z = p[2] + SCENE_Z_OFFSET;
    if (Math.abs(z) < 0.01) z = 0.01;
    return [[this.origin[0] + (p[0] * fov) / z, this.origin[1] + (p[1] * fov) / z], z];
  }

  /** screen pixel at camera depth → world point */
  unproject(sx, sy, depth, R = this.rotMat()) {
    const camZ = depth + SCENE_Z_OFFSET;
    const fov = SCENE_FOV * this.zoom;
    return mulT(R, [((sx - this.origin[0]) * camZ) / fov, ((sy - this.origin[1]) * camZ) / fov, depth]);
  }

  startStroke(hand, color, thickness) {
    this.current[hand] = { points: [], color, thickness };
  }

  addPoint(hand, sx, sy, depth) {
    this.current[hand]?.points.push(this.unproject(sx, sy, depth));
  }

  sprayPaint(hand, sx, sy, depth, radius, density, color, thickness) {
    this.current[hand] ??= { points: [], color, thickness, spray: true };
    const R = this.rotMat();
    for (let i = 0; i < density; i++) {
      const rx = Math.round((Math.random() * 2 - 1) * radius);
      const ry = Math.round((Math.random() * 2 - 1) * radius);
      if (rx * rx + ry * ry < radius * radius) this.current[hand].points.push(this.unproject(sx + rx, sy + ry, depth, R));
    }
  }

  finishStroke(hand) {
    const s = this.current[hand];
    if (s && s.points.length > 1) {
      this.strokes.push(s);
      this.redoStack = [];
    }
    this.current[hand] = null;
  }

  /** Erase in screen space along the swipe prev→(sx, sy). Splits lines, drops spray dots. */
  eraseAt(sx, sy, prev = null, radius = 40) {
    const R = this.rotMat();
    const hit = (pt) => {
      const [[px, py]] = this.project(pt, R);
      return segDist(px, py, sx, sy, prev) < radius;
    };
    const out = [];
    let erased = false;
    for (const s of this.strokes) {
      if (s.spray) {
        const keep = s.points.filter((p) => !hit(p));
        erased ||= keep.length < s.points.length;
        if (keep.length) out.push({ ...s, points: keep });
        continue;
      }
      let sub = [];
      for (const p of s.points) {
        if (hit(p)) {
          erased = true;
          if (sub.length > 1) out.push({ ...s, points: sub });
          sub = [];
        } else sub.push(p);
      }
      if (sub.length > 1) out.push({ ...s, points: sub });
    }
    if (erased) {
      this.strokes = out;
      this.redoStack = [];
    }
    return erased;
  }

  undo() {
    if (!this.strokes.length) return false;
    this.redoStack.push(this.strokes.pop());
    return true;
  }

  redo() {
    if (!this.redoStack.length) return false;
    this.strokes.push(this.redoStack.pop());
    return true;
  }

  clear() {
    this.strokes = [];
    this.redoStack = [];
    this.current = { Left: null, Right: null };
  }

  startRotate(sx, sy) {
    this.rotAnchor = [sx, sy];
    this.rotSnap = [...this.rotation];
  }

  updateRotate(sx, sy) {
    if (!this.rotAnchor) return;
    this.rotation[1] = this.rotSnap[1] + (sx - this.rotAnchor[0]) * ROT_SPEED;
    this.rotation[0] = Math.max(-90, Math.min(90, this.rotSnap[0] + (sy - this.rotAnchor[1]) * ROT_SPEED));
  }

  stopRotate() {
    this.rotAnchor = this.rotSnap = null;
  }

  adjustZoom(d) {
    this.zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, this.zoom + d));
  }

  // ── rendering ────────────────────────────────────────────
  render(ctx) {
    const R = this.rotMat();
    this._grid(ctx, R);
    this._strokes(ctx, R);
    this._cube(ctx, R);
    ctx.fillStyle = 'rgb(160,160,160)';
    ctx.font = '15px sans-serif';
    ctx.fillText(`Rot: (${this.rotation[0].toFixed(0)}, ${this.rotation[1].toFixed(0)})`, 10, this.h - 20);
    ctx.fillText(`Zoom: ${this.zoom.toFixed(1)}x`, 200, this.h - 20);
  }

  _seg(ctx, a, b, color, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }

  _grid(ctx, R) {
    const P = (p) => this.project(p, R)[0];
    for (let v = -2; v <= 2.01; v += 0.5) {
      this._seg(ctx, P([v, 0, -2]), P([v, 0, 2]), 'rgba(80,80,80,0.8)', 1);
      this._seg(ctx, P([-2, 0, v]), P([2, 0, v]), 'rgba(80,80,80,0.8)', 1);
    }
    const o = P([0, 0, 0]);
    const axes = [['X', [1, 0, 0], 'rgb(220,0,0)'], ['Y', [0, -1, 0], 'rgb(0,200,0)'], ['Z', [0, 0, 1], 'rgb(0,0,220)']];
    ctx.font = 'bold 15px sans-serif';
    for (const [lab, d, col] of axes) {
      this._seg(ctx, o, P(d.map((c) => c * 2.5)), col, 2);
      const t = P(d.map((c) => c * 2.7));
      ctx.fillStyle = col;
      ctx.fillText(lab, t[0], t[1]);
    }
  }

  _strokes(ctx, R) {
    const all = [...this.strokes];
    for (const hand of ['Left', 'Right']) if (this.current[hand]?.points.length > 1) all.push(this.current[hand]);
    const fade = (z) => Math.max(0.3, Math.min(1, 1 - (z - 2) * 0.1));
    const segs = [];
    for (const s of all) {
      if (s.spray) {
        const r = Math.max(1, s.thickness * 0.18);
        for (const pt of s.points) {
          const [[x, y], z] = this.project(pt, R);
          segs.push([z, x, y, null, s.color.map((c) => c * fade(z)), r]);
        }
        continue;
      }
      let [a, za] = this.project(s.points[0], R);
      for (let i = 1; i < s.points.length; i++) {
        const [b, zb] = this.project(s.points[i], R);
        const z = (za + zb) / 2;
        const width = Math.max(1, s.thickness / Math.max(0.5, z / SCENE_Z_OFFSET));
        segs.push([z, a, b, true, s.color.map((c) => c * fade(z)), width]);
        [a, za] = [b, zb];
      }
    }
    segs.sort((p, q) => q[0] - p[0]); // far → near
    ctx.lineCap = 'round';
    for (const [, a, b, isLine, col, size] of segs) {
      if (isLine) this._seg(ctx, a, b, rgb(col), size);
      else {
        ctx.fillStyle = rgb(col);
        ctx.fillRect(a - size, b - size, size * 2, size * 2);
      }
    }
  }

  _cube(ctx, R) {
    const sz = 25, cx = 70, cy = this.h - 70;
    const verts = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
    const p = verts.map((v) => mul(R, v));
    const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
    for (const [i, j] of edges) {
      const back = (p[i][2] + p[j][2]) / 2 < 0;
      this._seg(ctx, [cx + p[i][0] * sz, cy + p[i][1] * sz], [cx + p[j][0] * sz, cy + p[j][1] * sz],
        back ? 'rgb(90,90,90)' : 'rgb(190,190,190)', 1);
    }
  }
}
