# effects.py — Neon glow, particles, depth-pressure, freeze frame

import cv2
import numpy as np
from config import *


# ═══════════════════════════════════════════════════════════════
#  PARTICLES
# ═══════════════════════════════════════════════════════════════
class Particle:
    __slots__ = ['x', 'y', 'vx', 'vy', 'color', 'life', 'max_life', 'size']

    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        self.vx = np.random.uniform(-3, 3)
        self.vy = np.random.uniform(-5, -1)
        self.color = color
        self.life = np.random.randint(15, PARTICLE_LIFETIME)
        self.max_life = self.life
        self.size = np.random.randint(1, 4)


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []

    def emit(self, x, y, color, count=PARTICLE_COUNT):
        for _ in range(count):
            self.particles.append(Particle(x, y, color))

    def update_and_draw(self, frame):
        alive = []
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.15          # gravity
            p.vx *= 0.97          # drag
            p.life -= 1
            if p.life <= 0:
                continue
            alpha = p.life / p.max_life
            col = tuple(int(c * alpha) for c in p.color)
            cv2.circle(frame, (int(p.x), int(p.y)), p.size, col, -1, cv2.LINE_AA)
            alive.append(p)
        self.particles = alive


# ═══════════════════════════════════════════════════════════════
#  NEON GLOW
# ═══════════════════════════════════════════════════════════════
def apply_glow(canvas):
    """Return a copy of canvas with neon glow effect."""
    blur = cv2.GaussianBlur(canvas, (GLOW_BLUR, GLOW_BLUR), 0)
    glow = cv2.addWeighted(canvas, 1.0, blur, GLOW_INTENSITY, 0)
    # second pass for extra bloom
    blur2 = cv2.GaussianBlur(glow, (GLOW_BLUR * 2 + 1, GLOW_BLUR * 2 + 1), 0)
    return cv2.addWeighted(glow, 1.0, blur2, 0.3, 0)


def apply_glow_layer(canvas):
    """Return only the soft glow overlay to add on top of the sharp composite, optimized using downscaling."""
    h, w = canvas.shape[:2]
    # Downscale by 4x to make blur computationally efficient (16x speedup!)
    small = cv2.resize(canvas, (w // 4, h // 4), interpolation=cv2.INTER_LINEAR)
    # Blur the downscaled image
    blur = cv2.GaussianBlur(small, (9, 9), 0)
    # Upscale back to original resolution with smooth linear interpolation
    large = cv2.resize(blur, (w, h), interpolation=cv2.INTER_LINEAR)
    return large


# ═══════════════════════════════════════════════════════════════
#  DEPTH PRESSURE
# ═══════════════════════════════════════════════════════════════
def depth_to_pressure(z, base_size):
    """Map MediaPipe z-depth to brush size multiplier.
    Closer to camera (more negative z) → thicker brush.
    """
    # z typically ranges from -0.15 (close) to 0.05 (far)
    # map to multiplier 0.4 → 2.0
    multiplier = 1.0 + (-z * 8)
    multiplier = max(0.4, min(2.5, multiplier))
    return max(1, int(base_size * multiplier))


# ═══════════════════════════════════════════════════════════════
#  FREEZE FRAME
# ═══════════════════════════════════════════════════════════════
class FreezeFrame:
    def __init__(self):
        self.frozen = False
        self.frame = None

    def freeze(self, frame):
        self.frozen = True
        self.frame = frame.copy()

    def unfreeze(self):
        self.frozen = False
        self.frame = None

    def toggle(self, frame):
        if self.frozen:
            self.unfreeze()
        else:
            self.freeze(frame)
