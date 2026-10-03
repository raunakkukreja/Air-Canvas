# scene_3d.py — 3D drawing engine (strokes, rotation, projection)

import cv2
import numpy as np
from config import *


class Scene3D:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.strokes = []          # [{points:[(x,y,z),...], color, thickness}, ...]
        self.redo_stack = []
        self.current = {"Left": None, "Right": None}
        self.prev_3d = {}

        # view
        self.rotation = [0.0, 0.0, 0.0]   # pitch, yaw, roll (degrees)
        self.zoom = 1.0
        self.origin = (w // 2, h // 2)

        # rotation gesture state
        self._rot_anchor = None
        self._rot_snap = None

        # Cache for rotation matrix to avoid massive redundant allocations
        self._last_rotation = None
        self._cached_rot_mat = None

    # ── rotation matrix ───────────────────────────────────────
    def _rot_mat(self):
        """
        Calculate rotation matrix from pitch, yaw, roll angles.
        Uses cached computation for performance.
        """
        if self._cached_rot_mat is None or self.rotation != self._last_rotation:
            self._last_rotation = list(self.rotation)
            rx, ry, rz = np.radians(self.rotation)
            cx, sx = np.cos(rx), np.sin(rx)
            cy, sy = np.cos(ry), np.sin(ry)
            cz, sz = np.cos(rz), np.sin(rz)
            # Rotation matrices for each axis
            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
            Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
            self._cached_rot_mat = Rz @ Ry @ Rx
        return self._cached_rot_mat

    # ── projection ────────────────────────────────────────────
    def project(self, pt):
        """3D world point → (screen_xy, depth) with perspective projection."""
        p = self._rot_mat() @ np.array(pt, dtype=np.float64)
        fov = SCENE_FOV * self.zoom
        z = p[2] + SCENE_Z_OFFSET
        if abs(z) < 0.01:
            z = 0.01  # prevent division by zero
        sx = int(self.origin[0] + p[0] * fov / z)
        sy = int(self.origin[1] + p[1] * fov / z)
        return (sx, sy), z

    def unproject(self, cursor_3d):
        """Camera‑space cursor → world space (inverse rotation)."""
        return tuple(self._rot_mat().T @ np.array(cursor_3d, dtype=np.float64))

    # ── stroke ops ────────────────────────────────────────────
    def start_stroke(self, hand, color, thickness):
        self.current[hand] = {"points": [], "color": color, "thickness": thickness}

    def add_point(self, hand, sx, sy, depth_z):
        s = self.current[hand]
        if s is None:
            return
        cam_z = depth_z + SCENE_Z_OFFSET
        fov = SCENE_FOV * self.zoom
        cam_x = (sx - self.origin[0]) * cam_z / fov
        cam_y = (sy - self.origin[1]) * cam_z / fov
        cam_pt = np.array([cam_x, cam_y, depth_z], dtype=np.float64)
        world_pt = tuple(self._rot_mat().T @ cam_pt)
        s["points"].append(world_pt)

    def spray_paint(self, hand, sx, sy, depth_z, radius, density, color, thickness):
        if self.current[hand] is None:
            self.current[hand] = {"points": [], "color": color, "thickness": thickness, "spray": True}
        s = self.current[hand]
        
        # 1. Generate 2D circular offsets in screen pixels (EXACTLY like 2D spray!)
        rx = np.random.randint(-radius, radius + 1, density)
        ry = np.random.randint(-radius, radius + 1, density)
        inside = (rx * rx + ry * ry) < (radius * radius)
        rx = rx[inside]
        ry = ry[inside]
        
        spx = sx + rx
        spy = sy + ry
        
        # 2. Vectorized unprojection to 3D world space at depth_z
        cam_z = depth_z + SCENE_Z_OFFSET
        fov = SCENE_FOV * self.zoom
        
        cam_x = (spx - self.origin[0]) * cam_z / fov
        cam_y = (spy - self.origin[1]) * cam_z / fov
        cam_z_arr = np.full_like(spx, depth_z, dtype=np.float64)
        
        # Stack into camera space points: (N, 3) and rotate to world space
        cam_pts = np.stack([cam_x, cam_y, cam_z_arr], axis=-1)
        world_pts = cam_pts @ self._rot_mat()
        
        s["points"].extend(map(tuple, world_pts))

    def finish_stroke(self, hand):
        s = self.current[hand]
        if s is not None and len(s["points"]) > 1:
            self.strokes.append(s)
            self.redo_stack.clear()
        self.current[hand] = None

    def erase_at(self, sx, sy, depth_z, prev_pos=None, radius=40):
        # We perform the erase check in 2D screen space to solve the depth-mismatch issue!
        # This makes the 3D eraser behave exactly like the 2D eraser.
        A = np.array([sx, sy], dtype=np.float64)
        if prev_pos is not None:
            B = np.array([prev_pos[0], prev_pos[1]], dtype=np.float64)
            AB = B - A
            ab_sq = AB[0]**2 + AB[1]**2
        else:
            AB = None
            ab_sq = 0.0

        new_strokes = []
        erased = False

        for stroke in self.strokes:
            pts, col, th = stroke["points"], stroke["color"], stroke["thickness"]
            is_spray = stroke.get("spray", False)
            
            if is_spray:
                # Spray points are individual dots, no lines connect them.
                # Just filter out any dots that are within the eraser radius.
                remaining_pts = []
                for pt in pts:
                    (pt_sx, pt_sy), _ = self.project(pt)
                    if AB is not None and ab_sq > 1e-6:
                        ap_x = pt_sx - A[0]
                        ap_y = pt_sy - A[1]
                        dot = ap_x * AB[0] + ap_y * AB[1]
                        t = max(0.0, min(1.0, dot / ab_sq))
                        cx = A[0] + t * AB[0]
                        cy = A[1] + t * AB[1]
                        dist = ((pt_sx - cx)**2 + (pt_sy - cy)**2)**0.5
                    else:
                        dist = ((pt_sx - A[0])**2 + (pt_sy - A[1])**2)**0.5
                    
                    if dist < radius:
                        erased = True
                    else:
                        remaining_pts.append(pt)
                if remaining_pts:
                    new_strokes.append({"points": remaining_pts, "color": col, "thickness": th, "spray": True})
            else:
                current_sub = []
                for pt in pts:
                    (pt_sx, pt_sy), _ = self.project(pt)
                    if AB is not None and ab_sq > 1e-6:
                        ap_x = pt_sx - A[0]
                        ap_y = pt_sy - A[1]
                        dot = ap_x * AB[0] + ap_y * AB[1]
                        t = max(0.0, min(1.0, dot / ab_sq))
                        cx = A[0] + t * AB[0]
                        cy = A[1] + t * AB[1]
                        dist = ((pt_sx - cx)**2 + (pt_sy - cy)**2)**0.5
                    else:
                        dist = ((pt_sx - A[0])**2 + (pt_sy - A[1])**2)**0.5
                    
                    if dist < radius:
                        if len(current_sub) > 1:
                            new_strokes.append({"points": current_sub, "color": col, "thickness": th})
                        current_sub = []
                        erased = True
                    else:
                        current_sub.append(pt)
                if len(current_sub) > 1:
                    new_strokes.append({"points": current_sub, "color": col, "thickness": th})

        if erased:
            self.strokes = new_strokes
            self.redo_stack.clear()
            return True
        return False

    def undo(self):
        if self.strokes:
            self.redo_stack.append(self.strokes.pop())
            return True
        return False

    def redo(self):
        if self.redo_stack:
            self.strokes.append(self.redo_stack.pop())
            return True
        return False

    def clear(self):
        self.strokes.clear()
        self.redo_stack.clear()
        self.current = {"Left": None, "Right": None}
        self.prev_3d = {}

    # ── rotation gesture ──────────────────────────────────────
    def start_rotate(self, sx, sy):
        """Begin rotation tracking from hand position."""
        self._rot_anchor = (sx, sy)
        self._rot_snap = list(self.rotation)

    def update_rotate(self, sx, sy):
        """Update rotation based on hand movement delta."""
        if self._rot_anchor is None:
            return
        dx = sx - self._rot_anchor[0]
        dy = sy - self._rot_anchor[1]
        # Smooth rotation speed for better control
        self.rotation[1] = self._rot_snap[1] + dx * ROT_SPEED
        self.rotation[0] = self._rot_snap[0] + dy * ROT_SPEED
        # Clamp pitch to reasonable range
        self.rotation[0] = max(-90, min(90, self.rotation[0]))

    def stop_rotate(self):
        """Stop rotation tracking."""
        self._rot_anchor = None
        self._rot_snap = None

    def adjust_zoom(self, delta):
        """Adjust zoom level with constraints."""
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom + delta))

    # ── rendering ─────────────────────────────────────────────
    def render(self, frame):
        self._draw_grid(frame)
        self._draw_strokes(frame)
        self._draw_cube(frame)
        # depth cursor hint
        self._draw_depth_hud(frame)

    def _draw_grid(self, frame):
        gc = (40, 40, 40)
        ac = [(0, 0, 200), (0, 200, 0), (200, 0, 0)]
        rng = 2
        step = 0.5
        v = -rng
        while v <= rng + 0.01:
            p1, _ = self.project((v, 0, -rng))
            p2, _ = self.project((v, 0, rng))
            cv2.line(frame, p1, p2, gc, 1, cv2.LINE_AA)
            p1, _ = self.project((-rng, 0, v))
            p2, _ = self.project((rng, 0, v))
            cv2.line(frame, p1, p2, gc, 1, cv2.LINE_AA)
            v += step
        o, _ = self.project((0, 0, 0))
        for i, end in enumerate([(2.5, 0, 0), (0, -2.5, 0), (0, 0, 2.5)]):
            e, _ = self.project(end)
            cv2.line(frame, o, e, ac[i], 2, cv2.LINE_AA)
        for i, (lab, pt) in enumerate(zip('XYZ', [(2.7, 0, 0), (0, -2.7, 0), (0, 0, 2.7)])):
            p, _ = self.project(pt)
            cv2.putText(frame, lab, p, cv2.FONT_HERSHEY_SIMPLEX, 0.5, ac[i], 2)

    def _draw_strokes(self, frame):
        segs = []
        all_s = list(self.strokes)
        for hand in ('Left', 'Right'):
            if self.current[hand] and len(self.current[hand]["points"]) > 1:
                all_s.append(self.current[hand])
        for stroke in all_s:
            pts, col, th = stroke["points"], stroke["color"], stroke["thickness"]
            is_spray = stroke.get("spray", False)
            if is_spray:
                for pt in pts:
                    p, z = self.project(pt)
                    df = max(0.3, min(1.0, 1.0 - (z - 2) * 0.1))
                    ac = tuple(int(c * df) for c in col)
                    cv2.circle(frame, p, max(1, int(th * 0.18)), ac, -1, cv2.LINE_AA)
            else:
                for i in range(len(pts) - 1):
                    p1, z1 = self.project(pts[i])
                    p2, z2 = self.project(pts[i + 1])
                    az = (z1 + z2) / 2
                    df = max(0.3, min(1.0, 1.0 - (az - 2) * 0.1))
                    ac = tuple(int(c * df) for c in col)
                    at = max(1, int(th * (1.0 / max(0.5, az / SCENE_Z_OFFSET))))
                    segs.append((az, p1, p2, ac, at))
        segs.sort(key=lambda s: -s[0])
        for _, p1, p2, col, th in segs:
            cv2.line(frame, p1, p2, col, th, cv2.LINE_AA)

    def _draw_cube(self, frame):
        sz = 25
        cx, cy = 70, self.h - 70
        verts = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                 (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
        R = self._rot_mat()
        proj = []
        for v in verts:
            p = R @ np.array(v, dtype=np.float64)
            proj.append((int(cx + p[0] * sz), int(cy + p[1] * sz), p[2]))
        edges = [(0, 1), (1, 2), (2, 3), (3, 0),
                 (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        for i, j in edges:
            c = (60, 60, 60) if (proj[i][2] + proj[j][2]) / 2 < 0 else (150, 150, 150)
            cv2.line(frame, proj[i][:2], proj[j][:2], c, 1, cv2.LINE_AA)
        # face labels
        for label, axis_pt, col in [('X', (1.5, 0, 0), (0, 0, 200)),
                                     ('Y', (0, -1.5, 0), (0, 200, 0)),
                                     ('Z', (0, 0, 1.5), (200, 0, 0))]:
            p = R @ np.array(axis_pt)
            px, py = int(cx + p[0] * sz), int(cy + p[1] * sz)
            cv2.putText(frame, label, (px - 5, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)

    def _draw_depth_hud(self, frame):
        cv2.putText(frame, f"Rot: ({self.rotation[0]:.0f}, {self.rotation[1]:.0f})",
                    (10, self.h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1)
        cv2.putText(frame, f"Zoom: {self.zoom:.1f}x",
                    (200, self.h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1)
