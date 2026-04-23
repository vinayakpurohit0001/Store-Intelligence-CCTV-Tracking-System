import cv2
import numpy as np

# ── Uniform colour ranges in HSV ─────────────────────────────────────
# Adjust these ranges to match the actual store uniform colours.
# Default: dark navy/black uniforms common in Indian retail.
UNIFORM_HSV_RANGES = [
    # (lower_hsv, upper_hsv, name)
    (np.array([100, 50,  20]), np.array([130, 255, 100]), 'navy'),
    (np.array([0,   0,   0 ]), np.array([180, 50,  60 ]), 'black'),
    (np.array([0,   0,  200]), np.array([180, 30,  255]), 'white'),
]

STAFF_UNIFORM_RATIO = 0.50   # >50% of torso pixels matching = staff (tuned iteratively to avoid flagging backpacks)

def is_staff(frame_bgr: np.ndarray, bbox_xyxy: np.ndarray) -> bool:
    '''Returns True if the person in bbox likely wears a staff uniform.
    Analyses the upper 60% of the bounding box (torso region).'''
    x1,y1,x2,y2 = [int(v) for v in bbox_xyxy]
    # Bound to frame size
    h_f, w_f = frame_bgr.shape[:2]
    x1 = max(0, x1); y1 = max(0, y1); x2 = min(w_f, x2); y2 = min(h_f, y2)
    h = y2 - y1
    # Crop torso region (upper 60% of box)
    torso = frame_bgr[y1 : y1 + int(h*0.6), x1:x2]
    if torso.size == 0: return False

    hsv   = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    total = torso.shape[0] * torso.shape[1]
    if total == 0: return False

    for lo, hi, _ in UNIFORM_HSV_RANGES:
        mask  = cv2.inRange(hsv, lo, hi)
        ratio = cv2.countNonZero(mask) / total
        if ratio >= STAFF_UNIFORM_RATIO:
            return True
    return False
