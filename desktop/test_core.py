# test_core.py — headless checks (no webcam): gestures, 2D canvas, 3D math, exports
# Run: python test_core.py

import os
import tempfile
import numpy as np
from mediapipe.framework.formats import landmark_pb2

from config import *
from hand_tracker import HandTracker
from canvas_2d import Canvas2D
from scene_3d import Scene3D
from export import save_canvas_2d, export_obj, export_threejs_html

FINGERS = {'index': (6, 8), 'middle': (10, 12), 'ring': (14, 16), 'pinky': (18, 20)}


class _Handed:
    def __init__(self, label):
        self.classification = [type('C', (), {'label': label})()]


def make_hand(up=(), thumb='in', pinch=False):
    """Synthetic 21-landmark hand. Wrist (0) at y=.8, middle MCP (9) at y=.6 → hand scale .2."""
    pts = [(0.5, 0.5)] * 21
    pts[0], pts[9], pts[5] = (0.5, 0.8), (0.5, 0.6), (0.45, 0.6)
    for name, (pip, tip) in FINGERS.items():
        x = {'index': .45, 'middle': .5, 'ring': .55, 'pinky': .6}[name]
        pts[pip] = (x, 0.55)
        pts[tip] = (x, 0.40 if name in up else 0.60)
    pts[2] = (0.38, 0.65)  # thumb base
    pts[4] = {'in': (0.45, 0.62), 'up': (0.30, 0.55), 'down': (0.30, 0.75)}[thumb]
    if pinch:
        pts[4] = (pts[8][0] + 0.01, pts[8][1])
    lms = landmark_pb2.NormalizedLandmarkList()
    for x, y in pts:
        lms.landmark.add(x=x, y=y, z=0.0)
    return lms


def classify(tracker, lms, label='Right'):
    res = type('R', (), {'multi_hand_landmarks': [lms], 'multi_handedness': [_Handed(label)]})()
    tracker._hands.process = lambda rgb: res
    tracker._history = {'Left': [], 'Right': []}
    return tracker.process(np.zeros((360, 640, 3), np.uint8))[0].gesture


def test_gestures():
    t = HandTracker()
    cases = {
        'draw': make_hand({'index'}),
        'two_finger': make_hand({'index', 'middle'}),
        'erase': make_hand({'index', 'middle', 'ring'}),
        'rock_sign': make_hand({'index', 'pinky'}),
        'pinky_only': make_hand({'pinky'}),
        'middle_only': make_hand({'middle'}),
        'five_fingers_up': make_hand({'index', 'middle', 'ring', 'pinky'}, thumb='up'),
        'rotate_3d': make_hand({'index', 'middle', 'ring', 'pinky'}, thumb='in'),
        'fist': make_hand(),
        'thumb_up': make_hand(thumb='up'),
        'thumb_down': make_hand(thumb='down'),
    }
    for want, lms in cases.items():
        got = classify(t, lms)
        assert got == want, f'{want}: got {got}'
    t.release()


def test_canvas_2d():
    c = Canvas2D(200, 100)
    c.draw_line('Right', (10, 10), (50, 10), (0, 0, 255), 3, False)
    c.finish_stroke('Right')
    assert c.canvas[10, 30, 2] > 0
    assert c.undo() and c.canvas.sum() == 0
    assert c.redo() and c.canvas[10, 30, 2] > 0
    c.symmetry = True
    c.draw_line('Right', (10, 50), (20, 50), (0, 255, 0), 3, True)
    assert c.glow_canvas[50, 185, 1] > 0, 'symmetry should mirror onto glow layer'
    c.clear()
    assert c.canvas.sum() == 0 and not c.strokes


def test_scene_3d_roundtrip():
    s = Scene3D(640, 480)
    s.rotation = [20.0, -35.0, 0.0]
    s.zoom = 1.4
    s.start_stroke('Right', (255, 0, 0), 4)
    for sx, sy in [(100, 200), (320, 240), (500, 90)]:
        s.add_point('Right', sx, sy, -0.3)
        (px, py), _ = s.project(s.current['Right']['points'][-1])
        assert abs(px - sx) <= 1 and abs(py - sy) <= 1, (sx, sy, px, py)
    s.finish_stroke('Right')
    assert len(s.strokes) == 1
    # erasing the middle point splits nothing usable from 3 points -> stroke shrinks
    assert s.erase_at(320, 240, -0.3, radius=10)
    assert all(len(st['points']) < 3 for st in s.strokes)
    s.render(np.zeros((480, 640, 3), np.uint8))


def test_exports():
    strokes = [{'points': [(0, 0, 0), (1, 1, 1)], 'color': (0, 0, 255), 'thickness': 3},
               {'points': [(0.5, 0.5, 0.5)] * 3, 'color': (20, 20, 20), 'thickness': 4, 'spray': True}]
    d = tempfile.mkdtemp()
    obj = export_obj(strokes, os.path.join(d, 'x.obj'))
    lines = open(obj).read().splitlines()
    assert sum(l.startswith('v ') for l in lines) == 5 and 'l 1 2' in lines and 'p 3 4 5' in lines
    html = open(export_threejs_html(strokes, os.path.join(d, 'x.html'))).read()
    assert '"#ff0000"' in html and '"#ffffff"' in html  # red BGR→hex, black→white on black bg
    cwd = os.getcwd()
    os.chdir(d)
    try:
        canvas = np.zeros((100, 200, 3), np.uint8)
        canvas[40:60, 40:60] = (0, 0, 255)
        for mode in ('raw', 'white', 'brick', 'white_brick'):
            assert os.path.exists(save_canvas_2d(canvas, np.zeros_like(canvas), 100, 200, mode))
    finally:
        os.chdir(cwd)


def test_main_loop_strokes():
    """Drive main() with a fake camera + scripted gestures: draw, fist, draw, two_finger (glow on)."""
    import main
    from hand_tracker import HandData
    script = ([('draw', 300 + 10 * i) for i in range(5)] + [('fist', 400)] * 2 +
              [('draw', 600 + 10 * i) for i in range(5)] + [('two_finger', 640)])

    def hand(g, x):
        hd = HandData()
        hd.label, hd.gesture, hd.sx, hd.sy, hd.index_up = 'Right', g, x, 300, True
        return hd

    frames = iter(script)
    made = {}

    class Cap:
        def set(self, *a): pass
        def release(self): pass
        def read(self):
            self.step = next(frames, None)
            return self.step is not None, np.zeros((480, 960, 3), np.uint8)

    cap = Cap()
    keys = iter([ord('g')])  # turn glow on after the first frame
    patches = {
        'cv2.VideoCapture': lambda *a: cap, 'cv2.namedWindow': lambda *a: None,
        'cv2.setWindowProperty': lambda *a: None, 'cv2.imshow': lambda *a: None,
        'cv2.destroyAllWindows': lambda: None, 'cv2.waitKey': lambda d: next(keys, -1),
        'HandTracker': lambda: type('T', (), {'process': lambda s, f: [hand(*cap.step)]})(),
        'Canvas2D': lambda w, h: made.setdefault('c', Canvas2D(w, h)),
    }
    saved = {}
    for path, fake in patches.items():
        obj, attr = (main.cv2, path[4:]) if path.startswith('cv2.') else (main, path)
        saved[path] = (obj, attr, getattr(obj, attr))
        setattr(obj, attr, fake)
    try:
        main.main()
    finally:
        for obj, attr, orig in saved.values():
            setattr(obj, attr, orig)

    strokes = made['c'].strokes
    assert len(strokes) == 2, f'expected 2 strokes, got {len(strokes)}'
    assert all(s['glow'] for s in strokes), 'stroke ended by two_finger lost its glow flag'
    gaps = [abs(seg[1][0] - seg[0][0]) for s in strokes for seg in s['segments']]
    assert max(gaps) <= 10, f'stray line joined strokes across the fist (gap {max(gaps)}px)'


if __name__ == '__main__':
    for fn in [test_gestures, test_canvas_2d, test_scene_3d_roundtrip, test_exports, test_main_loop_strokes]:
        fn()
        print('ok', fn.__name__)
