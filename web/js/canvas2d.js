// canvas2d.js — 2D drawing engine: strokes, spray, undo/redo, symmetry (port of canvas_2d.py)
// Two transparent layers: matte ink and glow ink. Eraser = color null (punches through both).
import { W, H, DEFAULT_BRUSH_SIZE, DEFAULT_BRUSH_COLOR, rgb } from './config.js';

function layer() {
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  const ctx = c.getContext('2d');
  ctx.lineCap = ctx.lineJoin = 'round';
  return c;
}

export class Canvas2D {
  constructor() {
    this.canvas = layer();
    this.glowCanvas = layer();
    this.strokes = [];
    this.redoStack = [];
    this.current = { Left: [], Right: [] };
    this.prev = {};
    this.brushSize = DEFAULT_BRUSH_SIZE;
    this.brushColor = DEFAULT_BRUSH_COLOR;
    this.brushMode = false;
    this.sprayOn = false;
    this.symmetry = false;
  }

  _line(p1, p2, color, th, glow) {
    const targets = color ? [glow ? this.glowCanvas : this.canvas] : [this.canvas, this.glowCanvas];
    for (const t of targets) {
      const ctx = t.getContext('2d');
      ctx.globalCompositeOperation = color ? 'source-over' : 'destination-out';
      ctx.strokeStyle = color ? rgb(color) : '#000';
      ctx.lineWidth = th;
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]);
      ctx.lineTo(p2[0], p2[1]);
      ctx.stroke();
    }
  }

  _dots(dots, color, glow) {
    const ctx = (glow ? this.glowCanvas : this.canvas).getContext('2d');
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = rgb(color);
    for (const [x, y] of dots) ctx.fillRect(x - 1, y - 1, 3, 3);
  }

  drawLine(hand, p1, p2, color, thickness, glow) {
    this._line(p1, p2, color, thickness, glow);
    this.current[hand].push({ p1, p2, color, thickness });
    if (this.symmetry) {
      const m1 = [W - p1[0], p1[1]], m2 = [W - p2[0], p2[1]];
      this._line(m1, m2, color, thickness, glow);
      this.current[hand].push({ p1: m1, p2: m2, color, thickness });
    }
  }

  sprayPaint(hand, cx, cy, radius, density, color, glow) {
    const dots = [];
    for (let i = 0; i < density; i++) {
      const rx = Math.round((Math.random() * 2 - 1) * radius);
      const ry = Math.round((Math.random() * 2 - 1) * radius);
      if (rx * rx + ry * ry >= radius * radius) continue;
      const x = cx + rx, y = cy + ry;
      if (x < 0 || x >= W || y < 0 || y >= H) continue;
      dots.push([x, y]);
      if (this.symmetry) dots.push([W - x, y]);
    }
    if (!dots.length) return;
    this._dots(dots, color, glow);
    this.current[hand].push({ spray: dots, color });
  }

  finishStroke(hand, glow = false) {
    if (!this.current[hand].length) return;
    this.strokes.push({ segments: this.current[hand], glow });
    this.redoStack = [];
    this.current[hand] = [];
  }

  undo() {
    if (!this.strokes.length) return false;
    this.redoStack.push(this.strokes.pop());
    this._redraw();
    return true;
  }

  redo() {
    if (!this.redoStack.length) return false;
    this.strokes.push(this.redoStack.pop());
    this._redraw();
    return true;
  }

  clear() {
    this.strokes = [];
    this.redoStack = [];
    this.current = { Left: [], Right: [] };
    this.prev = {};
    this._wipe();
  }

  _wipe() {
    for (const c of [this.canvas, this.glowCanvas]) c.getContext('2d').clearRect(0, 0, W, H);
  }

  _redraw() {
    this._wipe();
    for (const { segments, glow } of this.strokes) {
      for (const s of segments) {
        if (s.spray) this._dots(s.spray, s.color, glow);
        else this._line(s.p1, s.p2, s.color, s.thickness, glow);
      }
    }
  }
}
