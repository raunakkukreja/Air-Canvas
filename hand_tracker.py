# hand_tracker.py — MediaPipe wrapper + gesture classification

import mediapipe as mp
import cv2
from config import *


class HandData:
    """Processed data for one detected hand."""
    __slots__ = [
        'label', 'landmarks', 'raw',
        'index_up', 'middle_up', 'ring_up', 'pinky_up',
        'index_curl', 'middle_curl', 'ring_curl', 'pinky_curl',
        'thumb_up', 'thumb_down',
        'x', 'y', 'z', 'sx', 'sy', 'sz',
        'hand_scale', 'gesture', 'cursor_3d',
    ]

    def __init__(self):
        self.label = ''
        self.landmarks = None
        self.raw = None
        self.index_up = self.middle_up = self.ring_up = self.pinky_up = False
        self.index_curl = self.middle_curl = self.ring_curl = self.pinky_curl = False
        self.thumb_up = self.thumb_down = False
        self.x = self.y = 0
        self.z = 0.0
        self.sx = self.sy = 0
        self.sz = 0.0
        self.hand_scale = 0.1
        self.gesture = 'none'
        self.cursor_3d = (0.0, 0.0, 0.0)


class HandTracker:
    def __init__(self):
        self._mp = mp.solutions.hands
        self._hands = self._mp.Hands(
            max_num_hands=MAX_HANDS,
            model_complexity=MODEL_COMPLEXITY,
            min_detection_confidence=MIN_DETECTION_CONF,
            min_tracking_confidence=MIN_TRACKING_CONF,
        )
        self.draw_utils = mp.solutions.drawing_utils
        self.hand_conns = self._mp.HAND_CONNECTIONS
        self._smooth = {}
        self._history = {'Left': [], 'Right': []}
        # Store previous frame data for better accuracy
        self._prev_state = {'Left': None, 'Right': None}

    # ─── public ───────────────────────────────────────────────
    def process(self, frame):
        """
        Process frame and return list of HandData objects for detected hands.
        Includes gesture classification, smoothing, and 3D cursor calculation.
        """
        h, w = frame.shape[:2]
        # Downscale frame for MediaPipe processing to boost FPS.
        # Landmarks are normalized (0.0 to 1.0), so downscaling doesn't affect accuracy.
        small_frame = cv2.resize(frame, (640, 360))
        rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        res = self._hands.process(rgb)
        out = []
        if not res.multi_hand_landmarks:
            return out
        for lms, handed in zip(res.multi_hand_landmarks, res.multi_handedness):
            hd = HandData()
            hd.label = handed.classification[0].label
            hd.raw = lms
            hd.landmarks = lm = lms.landmark

            # draw skeleton
            self.draw_utils.draw_landmarks(frame, lms, self.hand_conns)

            # key landmarks (tips and joints)
            idx, mid, ring, pink = lm[8], lm[12], lm[16], lm[20]   # fingertips
            tt, tb = lm[4], lm[2]                                   # thumb tip, thumb bottom

            hd.hand_scale = hs = max(abs(lm[9].y - lm[0].y), 0.05)

            # finger up detection (tip above pip joint by margin)
            hd.index_up = (lm[6].y - idx.y) / hs > FINGER_UP_THRESH
            hd.middle_up = (lm[10].y - mid.y) / hs > FINGER_UP_THRESH
            hd.ring_up = (lm[14].y - ring.y) / hs > FINGER_UP_THRESH
            hd.pinky_up = (lm[18].y - pink.y) / hs > FINGER_UP_THRESH

            # finger curl detection (tip below pip joint is robust)
            hd.index_curl = idx.y > lm[6].y
            hd.middle_curl = mid.y > lm[10].y
            hd.ring_curl = ring.y > lm[14].y
            hd.pinky_curl = pink.y > lm[18].y

            all_curl = (sum([hd.index_curl, hd.middle_curl, hd.ring_curl, hd.pinky_curl]) >= 3)
            # Distance between thumb tip and index knuckle, normalized by hand scale
            d_thumb = ((tt.x - lm[5].x)**2 + (tt.y - lm[5].y)**2)**0.5 / hs
            # Thumb is up/extended if d_thumb > THUMB_DISTANCE_THRESH and tip above bottom
            hd.thumb_up = all_curl and (d_thumb > THUMB_DISTANCE_THRESH) and (tb.y > tt.y)
            # Thumb is down if fingers are curled and thumb extended below other fingers
            hd.thumb_down = all_curl and (d_thumb > THUMB_DISTANCE_THRESH) and (tt.y > tb.y)

            # Classify raw gesture
            raw_g = self._classify(hd, tt, tb, d_thumb)

            # Track either index finger tip or middle finger tip depending on gesture
            if raw_g == 'middle_only':
                hd.x = int(mid.x * w)
                hd.y = int(mid.y * h)
                hd.z = mid.z
            else:
                hd.x = int(idx.x * w)
                hd.y = int(idx.y * h)
                hd.z = idx.z

            # Position smoothing for improved stability
            if hd.label not in self._smooth:
                self._smooth[hd.label] = (hd.x, hd.y, hd.z)
            ox, oy, oz = self._smooth[hd.label]
            hd.sx = int((1 - SMOOTH_FACTOR) * ox + SMOOTH_FACTOR * hd.x)
            hd.sy = int((1 - SMOOTH_FACTOR) * oy + SMOOTH_FACTOR * hd.y)
            hd.sz = (1 - SMOOTH_FACTOR) * oz + SMOOTH_FACTOR * hd.z
            self._smooth[hd.label] = (hd.sx, hd.sy, hd.sz)

            # 3D cursor in scene coordinates
            hd.cursor_3d = (
                (hd.sx - w / 2) / w * 4,
                (hd.sy - h / 2) / h * 3,
                -hd.sz * DEPTH_SCALE,
            )

            # Gesture smoothing via history (voting)
            self._history[hd.label].append(raw_g)
            if len(self._history[hd.label]) > 5:
                self._history[hd.label].pop(0)
            hd.gesture = max(set(self._history[hd.label]), key=self._history[hd.label].count)
            out.append(hd)
        return out

    def release(self):
        self._hands.close()

    # ─── private ──────────────────────────────────────────────
    def _classify(self, hd, tt, tb, d_thumb):
        """
        Classify hand gesture based on finger positions and curls.
        
        Gestures (priority order):
        - five_fingers_up: All 5 fingers fully extended (free mode for drawing)
        - rotate_3d: 4 fingers up + thumb CLOSED (3D rotation - ONLY method!)
        - open_palm: 4 fingers up + thumb up (color/brush selection)
        - rock_sign: Index + Pinky up, middle + ring down
        - erase: Index + Middle + Ring up, pinky down
        - two_finger: Index + Middle up, ring + pinky down
        - draw: Only index up (all others FULLY curled)
        - pinky_only: Only pinky up (all others FULLY curled)
        - middle_only: Only middle up (all others FULLY curled)
        - thumb_up/down/fist: All 4 fingers curled
        - pinch: Thumb + Index close
        """
        # Check if all 4 fingers are curled FIRST
        all_curl = hd.index_curl and hd.middle_curl and hd.ring_curl and hd.pinky_curl
        
        # 1. FIVE FINGERS UP (all 5 fingers fully extended, none curled)
        if hd.index_up and hd.middle_up and hd.ring_up and hd.pinky_up and not all_curl:
            # Also verify thumb is extended (not closed)
            if d_thumb > THUMB_DISTANCE_THRESH:
                return 'five_fingers_up'

        # 2. 4 fingers up + thumb CLOSED (ONLY way to rotate in 3D)
        if hd.index_up and hd.middle_up and hd.ring_up and hd.pinky_up:
            # Check if thumb is closed/tucked (not extended)
            lm = hd.landmarks
            if d_thumb < THUMB_DISTANCE_THRESH or tt.y >= lm[5].y:
                return 'rotate_3d'  # Thumb is closed - rotation gesture
            return 'open_palm'  # 4 fingers up + thumb up - color selection

        # 3. rock sign (index and pinky up, middle and ring fully curled)
        if hd.index_up and hd.pinky_up and not hd.middle_up and not hd.ring_up:
            if hd.middle_curl and hd.ring_curl:
                return 'rock_sign'

        # 4. erase (index, middle, ring up, pinky fully curled)
        if hd.index_up and hd.middle_up and hd.ring_up and not hd.pinky_up:
            if hd.pinky_curl:
                return 'erase'

        # 5. two_finger (index, middle up, ring and pinky fully curled)
        if hd.index_up and hd.middle_up and not hd.ring_up and not hd.pinky_up:
            if hd.ring_curl and hd.pinky_curl:
                return 'two_finger'

        # 6. draw (ONLY index up, all others FULLY curled - STRICT!)
        if hd.index_up and not hd.middle_up and not hd.ring_up and not hd.pinky_up:
            if hd.middle_curl and hd.ring_curl and hd.pinky_curl:
                return 'draw'

        # 7. pinky_only (ONLY pinky up, all others FULLY curled)
        if hd.pinky_up and not hd.index_up and not hd.middle_up and not hd.ring_up:
            if hd.index_curl and hd.middle_curl and hd.ring_curl:
                return 'pinky_only'

        # 8. middle_only (ONLY middle up, all others FULLY curled)
        if hd.middle_up and not hd.index_up and not hd.ring_up and not hd.pinky_up:
            if hd.index_curl and hd.ring_curl and hd.pinky_curl:
                return 'middle_only'

        # 9. fist / thumbs up / thumbs down (all 4 fingers curled/closed)
        if all_curl:
            if hd.thumb_up:
                return 'thumb_up'
            if hd.thumb_down:
                return 'thumb_down'
            return 'fist'

        # 10. pinch
        lm = hd.landmarks
        d = ((lm[4].x - lm[8].x) ** 2 + (lm[4].y - lm[8].y) ** 2) ** 0.5
        if d < 0.05 and not hd.middle_up and not hd.ring_up and not hd.pinky_up:
            return 'pinch'

        return 'none'
