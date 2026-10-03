# config.py — All settings and constants for Air Canvas

# ── Camera ──
CAM_INDEX = 0
CAM_WIDTH = 1920
CAM_HEIGHT = 1080
CAM_FPS = 60
CAM_BUFFER = 1

# ── MediaPipe ──
MAX_HANDS = 2
MODEL_COMPLEXITY = 1
MIN_DETECTION_CONF = 0.8  # improved from 0.75
MIN_TRACKING_CONF = 0.95  # improved from 0.9

# ── Drawing defaults ──
DEFAULT_BRUSH_SIZE = 6
DEFAULT_BRUSH_COLOR = (255, 0, 255)
MIN_BRUSH_SIZE = 2
MAX_BRUSH_SIZE = 30
ERASER_SIZE = 20
ERASER_COLOR = (0, 0, 0)

# ── Smoothing ──
SMOOTH_FACTOR = 0.80  # improved from 0.85 for better accuracy

# ── Hold durations (seconds) ──
SPRAY_TOGGLE_HOLD = 1.5
UNDO_REDO_HOLD = 0.7
CLEAR_HOLD_TIME = 2.0
THUMB_UP_HOLD = 1.5
SAVE_HOVER_HOLD = 0.7
MODE_SWITCH_HOLD = 1.5
SYMMETRY_TOGGLE_HOLD = 1.5
FREEZE_HOLD = 1.0

# ── Gesture thresholds (improved for accuracy) ──
FINGER_UP_THRESH = 0.32  # improved from 0.3
FINGER_CURL_THRESH = 0.05
THUMB_UP_VERT = 0.8
THUMB_UP_HORIZ = 0.1
THUMB_DOWN_VERT = 0.5
THUMB_DOWN_HORIZ = 0.12
THUMB_DISTANCE_THRESH = 0.35  # distance for thumb closed detection

# ── Color palette (name, BGR, x-position) ──
COLORS_LIST = [
    ("red",    (0, 0, 255),   40),
    ("orange", (0, 165, 255), 90),
    ("yellow", (0, 255, 255), 140),
    ("green",  (0, 255, 0),   190),
    ("blue",   (255, 0, 0),   240),
    ("violet", (255, 0, 255), 290),
    ("white",  (255, 255, 255), 340),
    ("black",  (25, 25, 25),  390),
]

# ── 3D scene ──
SCENE_FOV = 800
SCENE_Z_OFFSET = 3.0
DEPTH_SCALE = 5.0
ROT_SPEED = 0.3
MIN_ZOOM = 0.3
MAX_ZOOM = 3.0

# ── Effects ──
GLOW_BLUR = 21
GLOW_INTENSITY = 0.7
PARTICLE_LIFETIME = 30
PARTICLE_COUNT = 5

# ── Modes ──
MODE_2D = "2D Canvas"
MODE_3D = "3D Canvas"
MODES = [MODE_2D, MODE_3D]

WINDOW_NAME = "Air Canvas"
