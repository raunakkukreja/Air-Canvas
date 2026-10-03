// ui.js — toolbar, menus, hold bars, FPS, particles, hand skeleton (port of ui_overlay.py + effects.py)
import { W, H, COLORS_LIST, MIN_BRUSH_SIZE, MAX_BRUSH_SIZE, MODE_2D, MODE_3D, SAVE_HOVER_HOLD,
         PARTICLE_LIFETIME, TOOLBAR_H, rgb, sameColor } from './config.js';

export function put(ctx, text, x, y, scale = 0.5, color = 'white') {
  ctx.font = `bold ${Math.round(scale * 32)}px system-ui, sans-serif`;
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

const inBox = (p, x1, y1, x2, y2) => p && x1 < p[0] && p[0] < x2 && y1 < p[1] && p[1] < y2;

// ── toolbar ─────────────────────────────────────────────────
export function drawToolbar(ctx, s) {
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.fillRect(0, 0, W, TOOLBAR_H);
  for (const [, col, cx] of COLORS_LIST) {
    ctx.beginPath();
    ctx.arc(cx, 30, 16, 0, Math.PI * 2);
    ctx.fillStyle = rgb(col);
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#999';
    ctx.stroke();
    if (sameColor(col, s.brushColor)) {
      ctx.beginPath();
      ctx.arc(cx, 30, 20, 0, Math.PI * 2);
      ctx.lineWidth = 3;
      ctx.strokeStyle = '#e6b800';
      ctx.stroke();
    }
  }
  put(ctx, '🖌 BRUSH', 425, 37, 0.55, '#000');
  if (s.brushMode) {
    ctx.strokeStyle = '#666';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(560, 30);
    ctx.lineTo(760, 30);
    ctx.stroke();
    const knob = 560 + ((s.brushSize - MIN_BRUSH_SIZE) / (MAX_BRUSH_SIZE - MIN_BRUSH_SIZE)) * 200;
    ctx.beginPath();
    ctx.arc(knob, 30, 8, 0, Math.PI * 2);
    ctx.fillStyle = '#00c8c8';
    ctx.fill();
    put(ctx, `Size:${s.brushSize}`, 770, 37, 0.5, '#000');
  }
  put(ctx, 'SPRAY:', W - 330, 37, 0.52, '#000');
  put(ctx, s.sprayOn ? 'ON' : 'OFF', W - 240, 37, 0.52, s.sprayOn ? '#009600' : '#c80000');
  put(ctx, 'SYM', W - 170, 37, 0.52, s.symmetry ? '#00a0a0' : '#000');
  put(ctx, 'GLOW', W - 110, 37, 0.52, s.glowOn ? '#ff32b4' : '#000');
  put(ctx, s.mode, W / 2 - 60, 58, 0.5, s.mode === MODE_3D ? '#0078ff' : '#ff7800');
  if (s.symmetry && s.mode === MODE_2D) {
    ctx.strokeStyle = 'rgba(0,0,0,0.6)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(W / 2, TOOLBAR_H);
    ctx.lineTo(W / 2, H);
    ctx.stroke();
  }
}

export function drawHoldBar(ctx, label, hold, total, color) {
  const x = W / 2 - 200, y = H - 60;
  ctx.fillStyle = color;
  ctx.fillRect(x, y, Math.min(1, hold / total) * 400, 30);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, 400, 30);
  put(ctx, `${label}: ${Math.max(0, total - hold).toFixed(1)}s`, W / 2 - 100, H - 37, 0.65);
}

export class FPSCounter {
  constructor() {
    this.prev = performance.now();
    this.buf = [];
    this.fps = 0;
  }
  tick() {
    const now = performance.now();
    const dt = now - this.prev;
    this.prev = now;
    if (dt > 0) this.buf.push(1000 / dt);
    if (this.buf.length > 30) this.buf.shift();
    this.fps = this.buf.reduce((a, b) => a + b, 0) / this.buf.length;
  }
  draw(ctx) {
    const col = this.fps >= 25 ? '#00c800' : this.fps >= 15 ? '#c8c800' : '#c80000';
    put(ctx, `FPS: ${this.fps.toFixed(0)}`, W - 130, H - 15, 0.5, col);
  }
}

/** A row of point-and-hold buttons. Returns the chosen mode once a button is held long enough. */
class HoverMenu {
  constructor() {
    this.active = false;
    this.hoverStart = {};
  }
  open() {
    this.active = true;
    this.hoverStart = {};
  }
  close() {
    this.active = false;
  }
  _buttons(ctx, finger, buttons, holdTime) {
    const now = performance.now() / 1000;
    for (const b of buttons) {
      const hovered = inBox(finger, b.x1, b.y1, b.x2, b.y2);
      const cancel = b.mode === 'cancel';
      ctx.fillStyle = cancel ? (hovered ? '#c80000' : '#8c0000') : hovered ? '#505050' : '#323232';
      ctx.fillRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1);
      ctx.strokeStyle = '#c8c8c8';
      ctx.lineWidth = 2;
      ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1);
      ctx.textAlign = 'center';
      put(ctx, b.label, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2 + 7, 0.55);
      ctx.textAlign = 'left';
      if (!hovered) {
        delete this.hoverStart[b.mode];
        continue;
      }
      if (!(b.mode in this.hoverStart)) this.hoverStart = { [b.mode]: now };
      const hold = now - this.hoverStart[b.mode];
      ctx.fillStyle = cancel ? '#ff5050' : '#00b400';
      ctx.fillRect(b.x1 + 2, b.y2 - 10, Math.min(1, hold / holdTime) * (b.x2 - b.x1 - 4), 6);
      if (hold >= holdTime) {
        this.close();
        return b.mode;
      }
    }
    return null;
  }
}

export class SaveMenu extends HoverMenu {
  drawAndCheck(ctx, finger, mode) {
    const opts = mode === MODE_3D
      ? [['VIEW 3D DARK', 'black'], ['VIEW 3D LIGHT', 'white'], ['X', 'cancel']]
      : [['RAW', 'raw'], ['WHITE', 'white'], ['WHITE BRICK', 'white_brick'], ['BRICK', 'brick'], ['X', 'cancel']];
    const bw = 180, bh = 90, gap = 20;
    const x0 = (W - (opts.length * bw + (opts.length - 1) * gap)) / 2, y0 = H / 2 - bh / 2;
    ctx.fillStyle = 'rgba(20,20,20,0.6)';
    ctx.fillRect(0, H / 2 - 120, W, 240);
    ctx.textAlign = 'center';
    put(ctx, 'POINT & HOLD TO SAVE', W / 2, H / 2 - 80, 0.7);
    ctx.textAlign = 'left';
    const buttons = opts.map(([label, m], i) => ({ label, mode: m, x1: x0 + i * (bw + gap), y1: y0, x2: x0 + i * (bw + gap) + bw, y2: y0 + bh }));
    const r = this._buttons(ctx, finger, buttons, SAVE_HOVER_HOLD);
    return r === 'cancel' ? null : r;
  }
}

export class ModeSelector extends HoverMenu {
  drawAndCheck(ctx, finger) {
    const x1 = W / 2 - 250, y1 = H / 2 - 100;
    ctx.fillStyle = 'rgba(20,20,20,0.7)';
    ctx.fillRect(x1, y1, 500, 200);
    ctx.strokeStyle = '#646464';
    ctx.lineWidth = 2;
    ctx.strokeRect(x1, y1, 500, 200);
    ctx.textAlign = 'center';
    put(ctx, 'SELECT DRAWING MODE', W / 2, y1 + 40, 0.6);
    ctx.textAlign = 'left';
    return this._buttons(ctx, finger, [
      { label: '2D Draw', mode: MODE_2D, x1: W / 2 - 210, y1: H / 2, x2: W / 2 - 20, y2: H / 2 + 60 },
      { label: '3D Draw', mode: MODE_3D, x1: W / 2 + 20, y1: H / 2, x2: W / 2 + 210, y2: H / 2 + 60 },
    ], 0.7);
  }
}

// ── particles (effects.py) ──────────────────────────────────
export class ParticleSystem {
  constructor() {
    this.ps = [];
  }
  emit(x, y, color, count = 5) {
    for (let i = 0; i < count; i++) {
      const life = 15 + Math.floor(Math.random() * (PARTICLE_LIFETIME - 15));
      this.ps.push({ x, y, vx: Math.random() * 6 - 3, vy: Math.random() * 4 - 5, color, life, max: life,
                     size: 1 + Math.floor(Math.random() * 3) });
    }
  }
  updateAndDraw(ctx) {
    this.ps = this.ps.filter((p) => {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.15;
      p.vx *= 0.97;
      if (--p.life <= 0) return false;
      ctx.fillStyle = rgb(p.color, p.life / p.max);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
      return true;
    });
  }
}

/** Closer to camera (more negative z) → thicker brush. */
export const depthToPressure = (z, base) => Math.max(1, Math.round(base * Math.max(0.4, Math.min(2.5, 1 - z * 8))));

const HAND_EDGES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11],
  [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];

export function drawHand(ctx, pts) {
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 2;
  for (const [a, b] of HAND_EDGES) {
    ctx.beginPath();
    ctx.moveTo(pts[a][0], pts[a][1]);
    ctx.lineTo(pts[b][0], pts[b][1]);
    ctx.stroke();
  }
  ctx.fillStyle = '#ff3030';
  for (const [x, y] of pts) ctx.fillRect(x - 2.5, y - 2.5, 5, 5);
}
