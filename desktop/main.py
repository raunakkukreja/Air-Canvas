# main.py — Air Canvas entry point
# ────────────────────────────────────────────────────────────
# Gesture reference:
#   ☝️  Index only              → Draw / Spray
#   ✋  All five fingers up     → Draw / Spray / Free mode
#   ✊  4 fingers + thumb CLOSED → ONLY way to Rotate 3D
#   🤟  Idx+Mid+Ring (no pk)   → Eraser
#   🤙  Pinky only (1.5 s)     → Toggle spray
#   ✌️  Right two‑finger 0.7s  → Undo
#   ✌️  Left  two‑finger 0.7s  → Redo
#   👍  Thumb up 2 s           → Save menu (ONLY)
#   👎  Thumb down 2 s         → Clear canvas (ONLY)
#
# Additional gestures:
#   ✊  Fist (hold 1 s)        → Mode selector (2D / 3D)
#   🤘  Rock sign (hold 1 s)   → Toggle symmetry (2D only)
#   🤚  Open palm              → Color select / Brush adjust (toolbar only)
#   🤏  Pinch (3D mode)        → Zoom in/out
# ────────────────────────────────────────────────────────────

import cv2
import numpy as np
import time

from config import *
from hand_tracker import HandTracker
from canvas_2d import Canvas2D
from scene_3d import Scene3D
from effects import ParticleSystem, apply_glow, apply_glow_layer, depth_to_pressure, FreezeFrame
from ui_overlay import (draw_toolbar, FPSCounter, SaveMenu, ModeSelector,
                        draw_hold_bar, put)
from export import save_canvas_2d, export_obj, export_threejs_html


def main():
    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAM_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, CAM_BUFFER)

    tracker = HandTracker()
    canvas2d = None
    scene3d = None
    particles = ParticleSystem()
    fps = FPSCounter()
    save_menu = SaveMenu()
    mode_sel = ModeSelector()
    freezer = FreezeFrame()

    mode = MODE_2D
    glow_on = False

    # hold timers
    spray_hold = 0
    clear_hold = 0
    thumb_up_hold = 0
    undo_start = 0; undo_time = 0
    redo_start = 0; redo_time = 0
    show_undo = 0
    fist_hold = 0; fist_hand_pos = (0, 0)
    rock_hold = 0
    freeze_hold = 0
    pinch_prev_dist = None
    prev_erase_3d = {'Left': None, 'Right': None}

    save_feedback = 0
    save_feedback_text = ''

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # freeze frame support
        if freezer.frozen:
            frame = freezer.frame.copy()
        else:
            frame = cv2.flip(frame, 1)

        h, w = frame.shape[:2]

        # lazy init
        if canvas2d is None:
            canvas2d = Canvas2D(w, h)
        if scene3d is None:
            scene3d = Scene3D(w, h)

        fps.tick()

        # ── collect hand data ─────────────────────────────────
        hands = tracker.process(frame)

        any_thumb_down = False
        any_thumb_up = False
        active_undo = False
        active_redo = False
        menu_finger = None       # finger position for save menu overlay

        for hd in hands:
            sx, sy = hd.sx, hd.sy
            g = hd.gesture

            # ── save menu mode — only track finger ────────
            if save_menu.active:
                if hd.index_up:
                    menu_finger = (sx, sy)
                continue

            # ── mode selector active — only track finger ──
            if mode_sel.active:
                if hd.index_up:
                    menu_finger = (sx, sy)
                continue

            # ── thumb gestures ────────────────────────────
            if g == 'thumb_down':
                any_thumb_down = True
                if mode == MODE_2D:
                    canvas2d.current[hd.label] = []
                    canvas2d.clear_prev(hd.label)
                continue

            if g == 'thumb_up':
                any_thumb_up = True
                if mode == MODE_2D:
                    canvas2d.current[hd.label] = []
                    canvas2d.clear_prev(hd.label)
                continue

            # ── fist → mode selector ──────────────────────
            if g == 'fist':
                now = time.time()
                if fist_hold == 0:
                    fist_hold = now
                    fist_hand_pos = (sx, sy)
                hold = now - fist_hold
                remaining = max(0, MODE_SWITCH_HOLD - hold)
                put(frame, f'MODE: {remaining:.1f}', (sx - 40, sy - 30), .6, (0, 0, 0), 2)
                if hold >= MODE_SWITCH_HOLD:
                    mode_sel.open(fist_hand_pos[0], fist_hand_pos[1])
                    fist_hold = 0
                continue
            else:
                fist_hold = 0

            # ── rock sign → symmetry toggle ───────────────
            if g == 'rock_sign' and mode == MODE_2D:
                now = time.time()
                if rock_hold == 0:
                    rock_hold = now
                hold = now - rock_hold
                remaining = max(0, SYMMETRY_TOGGLE_HOLD - hold)
                action = 'OFF' if canvas2d.symmetry else 'ON'
                put(frame, f'SYMMETRY {action}: {remaining:.1f}', (sx - 60, sy - 30), .5, (0, 200, 200), 2)
                if hold >= SYMMETRY_TOGGLE_HOLD:
                    canvas2d.symmetry = not canvas2d.symmetry
                    rock_hold = 0
                continue
            else:
                rock_hold = 0

            # ── pinky only → spray toggle (runs in both 2D and 3D) ──
            if g == 'pinky_only':
                now = time.time()
                if spray_hold == 0:
                    spray_hold = now
                hold = now - spray_hold
                remaining = max(0, SPRAY_TOGGLE_HOLD - hold)
                action = 'Turn OFF' if canvas2d.spray_on else 'Turn ON'
                put(frame, f'{action}: {remaining:.1f}s', (w - 330, 80), .48, (0, 0, 0), 2)
                if hold >= SPRAY_TOGGLE_HOLD:
                    canvas2d.spray_on = not canvas2d.spray_on
                    spray_hold = 0
                continue
            else:
                spray_hold = 0

            # ── two-finger → undo / redo ──────────────────
            if g == 'two_finger':
                # finish any in-progress stroke first
                if mode == MODE_2D and canvas2d.current[hd.label]:
                    canvas2d.finish_stroke(hd.label)
                elif mode == MODE_3D:
                    scene3d.finish_stroke(hd.label)

                if hd.label == 'Right':
                    active_undo = True
                else:
                    active_redo = True

            # ── cursor dot ────────────────────────────────
            cv2.circle(frame, (sx, sy), 10, canvas2d.brush_color, -1)
            cv2.circle(frame, (sx, sy), 10, (255, 255, 255), 1)

            # ── 3D MODE ──────────────────────────────────
            if mode == MODE_3D:
                # If pointing inside the toolbar area (sy < 62), allow choosing colors and size, do not rotate/zoom
                if sy < 62:
                    scene3d.stop_rotate()
                    if g == 'five_fingers_up' or g == 'open_palm' or g == 'middle_only':
                        for name, bgr, cx in COLORS_LIST:
                            if abs(sx - cx) < 25:
                                canvas2d.brush_color = bgr
                        if 420 < sx < 540:
                            canvas2d.brush_mode = True

                    # brush slider
                    if canvas2d.brush_mode:
                        if 550 < sx < 770:
                            ratio = (sx - 550) / 220
                            canvas2d.brush_size = max(MIN_BRUSH_SIZE,
                                                       min(MAX_BRUSH_SIZE, int(2 + ratio * 28)))
                        if g in ['draw', 'erase', 'fist']:
                            canvas2d.brush_mode = False
                    continue
                else:
                    # middle only → sample color from camera
                    if g == 'middle_only':
                        scene3d.stop_rotate()
                        sample = frame[max(0, sy-3):sy+3, max(0, sx-3):sx+3]
                        if sample.size > 0:
                            avg = sample.mean(axis=(0, 1)).astype(int)
                            picked = tuple(int(c) for c in avg)
                            # show picked color preview
                            cv2.circle(frame, (sx, sy - 25), 15, picked, -1)
                            cv2.circle(frame, (sx, sy - 25), 15, (255, 255, 255), 2, cv2.LINE_AA)
                            put(frame, 'PICK', (sx - 18, sy - 45), .4, (255, 255, 255), 1)
                            canvas2d.brush_color = picked
                        continue

                    # rotate_3d (4 fingers up + thumb CLOSED) → rotate (ONLY method!)
                    # Only rotates when below toolbar (sy >= 80)
                    if g == 'rotate_3d' and sy >= 80:
                        if scene3d._rot_anchor is None:
                            scene3d.start_rotate(sx, sy)
                        scene3d.update_rotate(sx, sy)
                        put(frame, 'ROTATING 🔄', (sx - 40, sy - 30), .5, (0, 200, 200), 2)
                        continue
                    else:
                        if g == 'rotate_3d':
                            # Stop rotation if moved to toolbar area
                            scene3d.stop_rotate()

                    # five_fingers_up in 3D mode → DO NOTHING
                    if g == 'five_fingers_up':
                        scene3d.stop_rotate()
                        continue

                    # pinch → zoom (Right hand zooms in, Left hand zooms out)
                    if g == 'pinch':
                        if hd.label == 'Right':
                            scene3d.adjust_zoom(0.015)
                            put(frame, 'ZOOM IN ⊕', (sx - 40, sy - 30), .5, (0, 200, 0), 2)
                        else:
                            scene3d.adjust_zoom(-0.015)
                            put(frame, 'ZOOM OUT ⊖', (sx - 40, sy - 30), .5, (0, 0, 200), 2)
                        continue

                # draw in 3D (ONLY with 'draw' gesture - strict index only)
                if g == 'draw':
                    prev_erase_3d[hd.label] = None
                    if canvas2d.spray_on:
                        # Distance-sensitive spray (based on hand distance from camera ONLY)
                        # Spray size is NOT affected by brush_size slider
                        lm = hd.landmarks
                        palm_size = abs(int((lm[9].y - lm[0].y) * h))
                        spray_radius = max(8, min(80, int(180 - palm_size)))
                        spray_density = max(20, min(100, spray_radius * 2))
                        scene3d.spray_paint(hd.label, sx, sy, -hd.sz * DEPTH_SCALE, spray_radius, spray_density, canvas2d.brush_color, 4)
                        particles.emit(sx, sy, canvas2d.brush_color, 2)
                    else:
                        # Regular drawing uses brush_size
                        if scene3d.current[hd.label] is None:
                            scene3d.start_stroke(hd.label, canvas2d.brush_color, canvas2d.brush_size)
                        scene3d.add_point(hd.label, sx, sy, -hd.sz * DEPTH_SCALE)
                        depth_pct = int(max(0, min(100, 50 + hd.sz * 200)))
                        put(frame, f'Depth: {depth_pct}%', (sx + 15, sy - 10), .4, (200, 200, 200), 1)
                elif g == 'erase':
                    curr_z = -hd.sz * DEPTH_SCALE
                    curr_pos = (sx, sy, curr_z)
                    prev_pos = prev_erase_3d[hd.label]
                    
                    scene3d.erase_at(sx, sy, curr_z, prev_pos=prev_pos)
                    
                    prev_erase_3d[hd.label] = curr_pos
                    put(frame, '3D ERASING ✂', (sx + 15, sy - 10), .4, (0, 0, 255), 1)
                else:
                    scene3d.finish_stroke(hd.label)
                    prev_erase_3d[hd.label] = None

                continue

            # ── 2D MODE ──────────────────────────────────

            # five_fingers_up and open_palm: hover over toolbar for selection ONLY (no painting)
            if g == 'five_fingers_up' or g == 'open_palm' or g == 'rotate_3d':
                if sy < 62:
                    for name, bgr, cx in COLORS_LIST:
                        if abs(sx - cx) < 25:
                            canvas2d.brush_color = bgr
                    if 420 < sx < 540:
                        canvas2d.brush_mode = True

            # camera color sampling: middle_only (only middle finger up) below toolbar (identical to 3D mode)
            elif g == 'middle_only':
                if sy > 62:
                    # sample a small region from the raw frame
                    sample = frame[max(0, sy-3):sy+3, max(0, sx-3):sx+3]
                    if sample.size > 0:
                        avg = sample.mean(axis=(0, 1)).astype(int)
                        picked = tuple(int(c) for c in avg)
                        # show picked color preview
                        cv2.circle(frame, (sx, sy - 25), 15, picked, -1)
                        cv2.circle(frame, (sx, sy - 25), 15, (255, 255, 255), 2)
                        put(frame, 'PICK', (sx - 18, sy - 45), .4, (255, 255, 255), 1)
                        canvas2d.brush_color = picked

            # brush slider
            if canvas2d.brush_mode:
                if 550 < sx < 770 and sy < 62:
                    ratio = (sx - 550) / 220
                    canvas2d.brush_size = max(MIN_BRUSH_SIZE,
                                               min(MAX_BRUSH_SIZE, int(2 + ratio * 28)))
                if g in ['draw', 'erase', 'fist']:
                    canvas2d.brush_mode = False

            # draw / spray / erase
            color = canvas2d.brush_color
            thick = depth_to_pressure(hd.z, canvas2d.brush_size)

            if g == 'erase':
                color = ERASER_COLOR
                thick = ERASER_SIZE

            if canvas2d.spray_on and g == 'draw':
                lm = hd.landmarks
                palm_size = abs(int((lm[9].y - lm[0].y) * h))
                spray_radius = max(8, min(80, int(180 - palm_size)))
                spray_density = max(20, min(100, spray_radius * 2))
                put(frame, f'SPRAY r:{spray_radius}', (w - 330, 80), .48, (0, 0, 0), 2)
                canvas2d.spray_paint(hd.label, sx, sy, spray_radius, spray_density, canvas2d.brush_color, glow_on)
                particles.emit(sx, sy, canvas2d.brush_color, 2)
                canvas2d.clear_prev(hd.label)

            elif g == 'draw' or g == 'erase':
                if g == 'erase':
                    p = canvas2d.get_prev(hd.label)
                    if p is not None:
                        canvas2d.draw_line(hd.label, p, (sx, sy), color, thick, glow_on)
                    canvas2d.set_prev(hd.label, (sx, sy))
                else:
                    # draw only (strict index with others closed)
                    p = canvas2d.get_prev(hd.label)
                    if p is not None:
                        canvas2d.draw_line(hd.label, p, (sx, sy), color, thick, glow_on)
                    canvas2d.set_prev(hd.label, (sx, sy))

            else:
                if g != 'two_finger':
                    canvas2d.clear_prev(hd.label)
                    canvas2d.finish_stroke(hd.label, glow_on)

        # ── thumb up → save menu ──────────────────────────
        if any_thumb_up and not save_menu.active:
            now = time.time()
            if thumb_up_hold == 0:
                thumb_up_hold = now
            hold = now - thumb_up_hold
            draw_hold_bar(frame, 'SAVE', hold, THUMB_UP_HOLD, (0, 180, 0))
            if hold >= THUMB_UP_HOLD:
                save_menu.open()
                thumb_up_hold = 0
        else:
            thumb_up_hold = 0

        # ── save menu logic ───────────────────────────────
        if save_menu.active:
            temp_frame = frame.copy()
            result = save_menu.draw_and_check(temp_frame, menu_finger, mode)
            if result:
                if mode == MODE_2D:
                    fname = save_canvas_2d(canvas2d.canvas, canvas2d.glow_canvas, h, w, result)
                else:
                    if result == 'black_html':
                        fname = export_threejs_html(scene3d.strokes, bg_color='black')
                    else:
                        fname = export_threejs_html(scene3d.strokes, bg_color='white')
                    # Also export standard OBJ
                    obj_f = export_obj(scene3d.strokes)
                    
                    # Automatically open the interactive HTML file in Google Chrome!
                    try:
                        import os
                        import webbrowser
                        import subprocess
                        abs_html = os.path.abspath(fname)
                        
                        # Search standard and user-local AppData directories (extremely common for Chrome!)
                        local_appdata = os.environ.get('LOCALAPPDATA', '')
                        user_chrome = os.path.join(local_appdata, r"Google\Chrome\Application\chrome.exe")
                        
                        chrome_paths = [
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                            user_chrome
                        ]
                        opened_chrome = False
                        for path in chrome_paths:
                            if os.path.exists(path):
                                subprocess.Popen([path, abs_html])
                                opened_chrome = True
                                break
                        if not opened_chrome:
                            try:
                                # Try fallback using registered chrome browser
                                webbrowser.get('google-chrome').open(abs_html)
                                opened_chrome = True
                            except Exception:
                                pass
                        if not opened_chrome:
                            webbrowser.open(abs_html)
                    except Exception as e:
                        print(f"Error opening interactive viewer: {e}")
                        
                    fname = f'{fname} + {obj_f}'
                save_feedback = time.time() + 2.5
                save_feedback_text = f'SAVED: {fname}'

        # ── clear all ─────────────────────────────────────
        if any_thumb_down and not save_menu.active:
            now = time.time()
            if clear_hold == 0:
                clear_hold = now
            hold = now - clear_hold
            draw_hold_bar(frame, 'CLEAR ALL', hold, CLEAR_HOLD_TIME, (0, 0, 220))
            if hold >= CLEAR_HOLD_TIME:
                if mode == MODE_2D:
                    canvas2d.clear()
                else:
                    scene3d.clear()
                clear_hold = 0
        else:
            clear_hold = 0

        # ── undo ──────────────────────────────────────────
        if active_undo and not any_thumb_down and not save_menu.active:
            now = time.time()
            if undo_start == 0:
                undo_start = now
            hold = now - undo_start
            put(frame, f'UNDO {max(0, UNDO_REDO_HOLD - hold):.1f}', (40, 100), .8, (0, 0, 200), 2)
            if hold >= UNDO_REDO_HOLD and now - undo_time > UNDO_REDO_HOLD + 0.1:
                undo_time = now
                undo_start = 0
                show_undo = now + 1
                if mode == MODE_2D:
                    canvas2d.undo()
                else:
                    scene3d.undo()
        else:
            undo_start = 0

        # ── redo ──────────────────────────────────────────
        if active_redo and not any_thumb_down and not save_menu.active:
            now = time.time()
            if redo_start == 0:
                redo_start = now
            hold = now - redo_start
            put(frame, f'REDO {max(0, UNDO_REDO_HOLD - hold):.1f}', (40, 130), .8, (0, 180, 0), 2)
            if hold >= UNDO_REDO_HOLD and now - redo_time > UNDO_REDO_HOLD + 0.1:
                redo_time = now
                redo_start = 0
                if mode == MODE_2D:
                    canvas2d.redo()
                else:
                    scene3d.redo()
        else:
            redo_start = 0

        if time.time() < show_undo:
            put(frame, 'UNDO!', (40, 100), .8, (0, 0, 200), 2)

        # ── compositing ───────────────────────────────────
        if mode == MODE_2D:
            # 1. Composite standard matte drawing
            mask = cv2.cvtColor(canvas2d.canvas, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
            mask_inv = cv2.bitwise_not(mask)
            bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
            fg = cv2.bitwise_and(canvas2d.canvas, canvas2d.canvas, mask=mask)
            out = cv2.add(bg, fg)

            # 2. Composite glow drawing (always composite it with glow!)
            g_mask = cv2.cvtColor(canvas2d.glow_canvas, cv2.COLOR_BGR2GRAY)
            _, g_mask = cv2.threshold(g_mask, 1, 255, cv2.THRESH_BINARY)
            g_mask_inv = cv2.bitwise_not(g_mask)
            
            out_bg = cv2.bitwise_and(out, out, mask=g_mask_inv)
            out_fg = cv2.bitwise_and(canvas2d.glow_canvas, canvas2d.glow_canvas, mask=g_mask)
            out = cv2.add(out_bg, out_fg)

            glow_layer = apply_glow_layer(canvas2d.glow_canvas)
            out = cv2.add(out, glow_layer)
        else:
            # 3D mode — render scene on top of camera
            out = frame.copy()
            scene3d.render(out)

        # ── save menu overlay on top of drawing ───────────
        if save_menu.active:
            save_menu.draw_and_check(out, menu_finger, mode)

        # ── particles on top ──────────────────────────────
        particles.update_and_draw(out)

        # ── toolbar ───────────────────────────────────────
        draw_toolbar(out, canvas2d.brush_color, canvas2d.brush_size,
                     canvas2d.brush_mode, canvas2d.spray_on,
                     canvas2d.symmetry, mode, glow_on)

        # ── FPS ───────────────────────────────────────────
        fps.draw(out)

        # ── mode selector overlay ─────────────────────────
        if mode_sel.active:
            sel = mode_sel.draw_and_check(out, menu_finger)
            if sel:
                mode = sel

        # save feedback flash
        if time.time() < save_feedback:
            put(out, save_feedback_text, (w // 2 - 300, h // 2), 1.0, (0, 220, 0), 3)

        # ── keyboard shortcuts ────────────────────────────
        cv2.imshow(WINDOW_NAME, out)
        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):
            break
        elif key == ord('g'):
            glow_on = not glow_on
        elif key == ord('f'):
            freezer.toggle(frame)
        elif key == ord('s'):
            canvas2d.symmetry = not canvas2d.symmetry

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
