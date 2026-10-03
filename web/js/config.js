// config.js — settings and constants (port of config.py). Colors are [r, g, b].

// Fixed drawing surface; the camera feed is cover-fitted into it.
export const W = 1280;
export const H = 720;

export const MAX_HANDS = 2;
export const MIN_DETECTION_CONF = 0.8;
export const MIN_TRACKING_CONF = 0.95;

export const DEFAULT_BRUSH_SIZE = 6;
export const DEFAULT_BRUSH_COLOR = [255, 0, 255];
export const MIN_BRUSH_SIZE = 2;
export const MAX_BRUSH_SIZE = 30;
export const ERASER_SIZE = 20;

export const SMOOTH_FACTOR = 0.8;

// hold durations (seconds)
export const SPRAY_TOGGLE_HOLD = 1.5;
export const UNDO_REDO_HOLD = 0.7;
export const CLEAR_HOLD_TIME = 2.0;
export const THUMB_UP_HOLD = 1.5;
export const SAVE_HOVER_HOLD = 0.7;
export const MODE_SWITCH_HOLD = 1.5;
export const SYMMETRY_TOGGLE_HOLD = 1.5;

// gesture thresholds
export const FINGER_UP_THRESH = 0.32;
export const THUMB_DISTANCE_THRESH = 0.35;

// palette: [name, rgb, toolbar x]
export const COLORS_LIST = [
  ['red', [255, 0, 0], 40],
  ['orange', [255, 165, 0], 90],
  ['yellow', [255, 255, 0], 140],
  ['green', [0, 255, 0], 190],
  ['blue', [0, 0, 255], 240],
  ['violet', [255, 0, 255], 290],
  ['white', [255, 255, 255], 340],
  ['black', [25, 25, 25], 390],
];
export const TOOLBAR_H = 62;

// 3D scene
export const SCENE_FOV = 800;
export const SCENE_Z_OFFSET = 3.0;
export const DEPTH_SCALE = 5.0;
export const ROT_SPEED = 0.3;
export const MIN_ZOOM = 0.3;
export const MAX_ZOOM = 3.0;

export const PARTICLE_LIFETIME = 30;

export const MODE_2D = '2D Canvas';
export const MODE_3D = '3D Canvas';

export const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
export const sameColor = (a, b) => a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
