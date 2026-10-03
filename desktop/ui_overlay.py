# ui_overlay.py — HUD, toolbar, menus, mode selector

import cv2
import numpy as np
import time
from config import *


def put(frame, text, pos, scale=0.5, color=(255, 255, 255), thick=2):
    cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


# ═══════════════════════════════════════════════════════════════
#  TOP TOOLBAR
# ═══════════════════════════════════════════════════════════════
def draw_toolbar(frame, brush_color, brush_size, brush_mode, spray_on, symmetry, mode, glow_on):
    w = frame.shape[1]

    # color palette
    for name, bgr, cx in COLORS_LIST:
        cv2.circle(frame, (cx, 30), 16, bgr, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, 30), 16, (255, 255, 255), 1, cv2.LINE_AA)
        # highlight selected
        if bgr == brush_color:
            cv2.circle(frame, (cx, 30), 19, (0, 255, 255), 2, cv2.LINE_AA)

    # brush icon + label
    _draw_brush_icon(frame, 430, 24)
    put(frame, 'BRUSH', (452, 36), .52, (0, 0, 0), 2)

    # brush slider
    if brush_mode:
        cv2.line(frame, (560, 30), (760, 30), (100, 100, 100), 2, cv2.LINE_AA)
        knob = 560 + int((brush_size - MIN_BRUSH_SIZE) / (MAX_BRUSH_SIZE - MIN_BRUSH_SIZE) * 200)
        cv2.circle(frame, (knob, 30), 8, (0, 200, 200), -1, cv2.LINE_AA)
        put(frame, f'Size:{brush_size}', (770, 36), .5, (0, 0, 0), 2)

    # spray status
    sx = w - 330
    _draw_spray_icon(frame, sx, 24)
    put(frame, 'SPRAY:', (sx + 32, 36), .52, (0, 0, 0), 2)
    s_col = (0, 150, 0) if spray_on else (0, 0, 200)
    put(frame, 'ON' if spray_on else 'OFF', (sx + 115, 36), .52, s_col, 2)

    # symmetry indicator
    sym_x = w - 170
    sym_col = (0, 180, 180) if symmetry else (0, 0, 0)
    put(frame, 'SYM', (sym_x, 36), .52, sym_col, 2)
    if symmetry:
        cv2.line(frame, (w // 2, 62), (w // 2, frame.shape[0]), (0, 0, 0), 1, cv2.LINE_AA)

    # glow indicator
    glow_x = w - 110
    glow_col = (180, 50, 255) if glow_on else (0, 0, 0)
    put(frame, 'GLOW', (glow_x, 36), .52, glow_col, 2)

    # mode badge
    mode_col = (255, 120, 0) if mode == MODE_3D else (0, 120, 255)
    put(frame, mode, (w // 2 - 40, 50), .55, mode_col, 2)


def _draw_brush_icon(frame, x, y):
    cv2.line(frame, (x, y - 10), (x + 10, y + 2), (0, 0, 0), 2, cv2.LINE_AA)
    cv2.rectangle(frame, (x + 8, y), (x + 13, y + 5), (80, 80, 80), -1)
    pts = np.array([[x + 12, y + 3], [x + 16, y + 10], [x + 8, y + 10]], np.int32)
    cv2.fillPoly(frame, [pts], (0, 0, 0), cv2.LINE_AA)


def _draw_spray_icon(frame, x, y):
    cv2.rectangle(frame, (x, y - 2), (x + 10, y + 12), (80, 80, 80), -1)
    cv2.rectangle(frame, (x, y - 2), (x + 10, y + 12), (0, 0, 0), 1)
    cv2.rectangle(frame, (x + 8, y - 6), (x + 12, y), (0, 0, 0), -1)
    for dx, dy in [(18, -4), (20, 1), (22, -7), (24, 3), (26, -3)]:
        cv2.circle(frame, (x + dx, y + dy), 2, (0, 0, 0), -1, cv2.LINE_AA)


# ═══════════════════════════════════════════════════════════════
#  FPS / PERFORMANCE HUD
# ═══════════════════════════════════════════════════════════════
class FPSCounter:
    def __init__(self):
        self._prev = time.time()
        self._fps = 0
        self._buf = []

    def tick(self):
        now = time.time()
        dt = now - self._prev
        self._prev = now
        if dt > 0:
            self._buf.append(1.0 / dt)
        if len(self._buf) > 30:
            self._buf.pop(0)
        self._fps = sum(self._buf) / len(self._buf) if self._buf else 0

    def draw(self, frame):
        col = (0, 200, 0) if self._fps >= 25 else (0, 200, 200) if self._fps >= 15 else (0, 0, 200)
        put(frame, f'FPS: {self._fps:.0f}', (frame.shape[1] - 130, frame.shape[0] - 15), .5, col, 1)


# ═══════════════════════════════════════════════════════════════
#  SAVE MENU
# ═══════════════════════════════════════════════════════════════
class SaveMenu:
    def __init__(self):
        self.active = False
        self.hover_start = {}
        self._boxes = None
        self._prev_mode = None

    def open(self):
        self.active = True
        self.hover_start = {}
        self._boxes = None
        self._prev_mode = None

    def close(self):
        self.active = False
        self.hover_start = {}

    def get_boxes(self, w, h, current_mode):
        if self._boxes and self._prev_mode == current_mode:
            return self._boxes
        self._prev_mode = current_mode

        if current_mode == MODE_3D:
            # 3D save options: BLACK HTML, WHITE HTML, and Cancel
            labels = ['BLACK HTML', 'WHITE HTML', 'X']
            modes = ['black_html', 'white_html', 'cancel']
            bw, bh, gap = 200, 90, 20
            total_w = 3 * bw + 2 * gap
            sx = (w - total_w) // 2
            sy = h // 2 - bh // 2
            self._boxes = []
            for i in range(3):
                x1 = sx + i * (bw + gap)
                self._boxes.append({
                    'label': labels[i], 'mode': modes[i],
                    'x1': x1, 'y1': sy, 'x2': x1 + bw, 'y2': sy + bh,
                })
        else:
            # 2D save options
            labels = ['RAW', 'WHITE', 'WHITE BRICK', 'BRICK', 'X']
            modes = ['raw', 'white', 'white_brick', 'brick', 'cancel']
            bw, bh, gap = 180, 90, 20
            total_w = 5 * bw + 4 * gap
            sx = (w - total_w) // 2
            sy = h // 2 - bh // 2
            self._boxes = []
            for i in range(5):
                x1 = sx + i * (bw + gap)
                self._boxes.append({
                    'label': labels[i], 'mode': modes[i],
                    'x1': x1, 'y1': sy, 'x2': x1 + bw, 'y2': sy + bh,
                })
        return self._boxes

    def draw_and_check(self, frame, finger_pos, current_mode):
        """Draw save menu. Returns selected mode string or None."""
        h, w = frame.shape[:2]
        boxes = self.get_boxes(w, h, current_mode)

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h // 2 - 120), (w, h // 2 + 120), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        put(frame, 'POINT & HOLD TO SAVE', (w // 2 - 180, h // 2 - 80), 0.7, (255, 255, 255), 2)

        now = time.time()
        for box in boxes:
            x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
            mode = box['mode']
            is_cancel = mode == 'cancel'
            hovered = False
            if finger_pos:
                fx, fy = finger_pos
                if x1 < fx < x2 and y1 < fy < y2:
                    hovered = True

            bg = (0, 0, 140 if is_cancel else 50)
            if hovered:
                bg = (0, 0, 200) if is_cancel else (80, 80, 80)
            cv2.rectangle(frame, (x1, y1), (x2, y2), bg, -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 200), 2, cv2.LINE_AA)

            txt_x = x1 + (x2 - x1) // 2 - len(box['label']) * 7
            txt_y = y1 + (y2 - y1) // 2 + 8
            txt_c = (0, 0, 255) if is_cancel else (255, 255, 255)
            put(frame, box['label'], (txt_x, txt_y), .55, txt_c, 2)

            if hovered:
                if mode not in self.hover_start:
                    self.hover_start = {mode: now}
                hold = now - self.hover_start.get(mode, now)
                fill_w = int((hold / SAVE_HOVER_HOLD) * (x2 - x1 - 4))
                fill_c = (0, 0, 180) if is_cancel else (0, 180, 0)
                cv2.rectangle(frame, (x1 + 2, y2 - 12), (x1 + 2 + fill_w, y2 - 4), fill_c, -1)
                if hold >= SAVE_HOVER_HOLD:
                    self.close()
                    return None if is_cancel else mode
            else:
                if mode in self.hover_start:
                    del self.hover_start[mode]
        return None


# ═══════════════════════════════════════════════════════════════
#  MODE SELECTOR (radial menu on fist hold)
# ═══════════════════════════════════════════════════════════════
class ModeSelector:
    def __init__(self):
        self.active = False
        self.hover_start = {}

    def open(self, cx, cy):
        self.active = True
        self.hover_start = {}

    def close(self):
        self.active = False
        self.hover_start = {}

    def draw_and_check(self, frame, finger_pos):
        """Draw centered mode panel. Returns selected mode or None."""
        h, w = frame.shape[:2]
        now = time.time()
        
        # Centered placement: beautiful panel in the center
        x1, y1 = w // 2 - 250, h // 2 - 100
        x2, y2 = w // 2 + 250, h // 2 + 100

        # dark overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (100, 100, 100), 2, cv2.LINE_AA)

        put(frame, "SELECT DRAWING MODE", (w // 2 - 120, y1 + 35), 0.55, (255, 255, 255), 2)

        buttons = [
            {"label": "2D Draw", "mode": MODE_2D, "bx1": w // 2 - 210, "bx2": w // 2 - 20},
            {"label": "3D Draw", "mode": MODE_3D, "bx1": w // 2 + 20, "bx2": w // 2 + 210},
        ]

        selected = None
        for btn in buttons:
            bx1, bx2 = btn["bx1"], btn["bx2"]
            by1, by2 = h // 2, h // 2 + 60
            mode = btn["mode"]

            hovered = False
            if finger_pos:
                fx, fy = finger_pos
                if bx1 < fx < bx2 and by1 < fy < by2:
                    hovered = True

            bg = (80, 80, 80) if hovered else (40, 40, 40)
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), bg, -1)
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), (150, 150, 150), 1, cv2.LINE_AA)

            put(frame, btn["label"], (bx1 + 45, by1 + 38), 0.5, (255, 255, 255), 2)

            if hovered:
                if mode not in self.hover_start:
                    self.hover_start = {mode: now}
                hold = now - self.hover_start.get(mode, now)
                fill_w = int((hold / 0.7) * (bx2 - bx1 - 4))
                cv2.rectangle(frame, (bx1 + 2, by2 - 6), (bx1 + 2 + fill_w, by2 - 2), (0, 180, 0), -1)
                if hold >= 0.7:
                    selected = mode
                    self.close()
            else:
                if mode in self.hover_start:
                    del self.hover_start[mode]

        return selected


# ═══════════════════════════════════════════════════════════════
#  HOLD PROGRESS BAR (reusable)
# ═══════════════════════════════════════════════════════════════
def draw_hold_bar(frame, label, hold, total, color=(0, 180, 0)):
    h, w = frame.shape[:2]
    remaining = max(0, total - hold)
    bar_w = int((hold / total) * 400)
    cv2.rectangle(frame, (w // 2 - 200, h - 60), (w // 2 - 200 + bar_w, h - 30), color, -1)
    cv2.rectangle(frame, (w // 2 - 200, h - 60), (w // 2 + 200, h - 30), color, 2)
    put(frame, f'{label}: {remaining:.1f}s', (w // 2 - 100, h - 35), .7, (255, 255, 255), 2)
