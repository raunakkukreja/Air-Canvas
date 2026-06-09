# canvas_2d.py — 2D drawing engine (strokes, spray, undo/redo, symmetry)

import cv2
import numpy as np
from config import *


class Canvas2D:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.canvas = np.zeros((h, w, 3), dtype=np.uint8)
        self.glow_canvas = np.zeros((h, w, 3), dtype=np.uint8)
        self.strokes = []
        self.redo_stack = []
        self.current = {"Left": [], "Right": []}
        self.prev = {}

        # brush state
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.brush_color = DEFAULT_BRUSH_COLOR
        self.brush_mode = False
        self.spray_on = False
        self.symmetry = False

    # ── drawing ───────────────────────────────────────────────
    def draw_line(self, hand, p1, p2, color, thickness, glow_on):
        if color == ERASER_COLOR:
            # Eraser should wipe out both layers!
            cv2.line(self.canvas, p1, p2, color, thickness, cv2.LINE_AA)
            cv2.line(self.glow_canvas, p1, p2, color, thickness, cv2.LINE_AA)
        else:
            target = self.glow_canvas if glow_on else self.canvas
            cv2.line(target, p1, p2, color, thickness, cv2.LINE_AA)

        self.current[hand].append((p1, p2, color, thickness))
        if self.symmetry:
            mp1 = (self.w - p1[0], p1[1])
            mp2 = (self.w - p2[0], p2[1])
            if color == ERASER_COLOR:
                cv2.line(self.canvas, mp1, mp2, color, thickness, cv2.LINE_AA)
                cv2.line(self.glow_canvas, mp1, mp2, color, thickness, cv2.LINE_AA)
            else:
                cv2.line(target, mp1, mp2, color, thickness, cv2.LINE_AA)
            self.current[hand].append((mp1, mp2, color, thickness))

    def spray_paint(self, hand, cx, cy, radius, density, color, glow_on):
        target = self.glow_canvas if glow_on else self.canvas
        # Generate random offsets inside the bounding box
        rx = np.random.randint(-radius, radius + 1, density)
        ry = np.random.randint(-radius, radius + 1, density)
        # Filter points that are within the circle
        inside = (rx * rx + ry * ry) < (radius * radius)
        rx = rx[inside]
        ry = ry[inside]
        
        spx = cx + rx
        spy = cy + ry
        
        # Clip to canvas boundary
        valid = (spx >= 0) & (spx < self.w) & (spy >= 0) & (spy < self.h)
        spx = spx[valid]
        spy = spy[valid]
        
        dots = []
        for x, y in zip(spx, spy):
            cv2.circle(target, (x, y), 1, color, -1)
            dots.append((x, y))
            if self.symmetry:
                mx = self.w - x
                if 0 <= mx < self.w:
                    cv2.circle(target, (mx, y), 1, color, -1)
                    dots.append((mx, y))
                    
        if dots:
            self.current[hand].append(('spray', dots, color))

    # ── stroke management ─────────────────────────────────────
    def finish_stroke(self, hand, glow_on=False):
        if self.current[hand]:
            self.strokes.append({"segments": self.current[hand][:], "glow": glow_on})
            self.redo_stack.clear()
            self.current[hand] = []

    def undo(self):
        if self.strokes:
            self.redo_stack.append(self.strokes.pop())
            self._redraw()
            return True
        return False

    def redo(self):
        if self.redo_stack:
            self.strokes.append(self.redo_stack.pop())
            self._redraw()
            return True
        return False

    def clear(self):
        self.canvas = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.glow_canvas = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.strokes.clear()
        self.redo_stack.clear()
        self.current = {"Left": [], "Right": []}
        self.prev = {}

    # ── helpers ────────────────────────────────────────────────
    def get_prev(self, hand):
        return self.prev.get(hand)

    def set_prev(self, hand, pos):
        self.prev[hand] = pos

    def clear_prev(self, hand):
        self.prev[hand] = None

    def _redraw(self):
        self.canvas = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.glow_canvas = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        for stroke in self.strokes:
            glow = stroke["glow"]
            target = self.glow_canvas if glow else self.canvas
            for seg in stroke["segments"]:
                if seg[0] == 'spray':
                    _, pts, col = seg
                    for px, py in pts:
                        if 0 <= px < self.w and 0 <= py < self.h:
                            cv2.circle(target, (px, py), 1, col, -1)
                elif len(seg) == 4:
                    p1, p2, col, th = seg
                    if col == ERASER_COLOR:
                        cv2.line(self.canvas, p1, p2, col, th, cv2.LINE_AA)
                        cv2.line(self.glow_canvas, p1, p2, col, th, cv2.LINE_AA)
                    else:
                        cv2.line(target, p1, p2, col, th, cv2.LINE_AA)
