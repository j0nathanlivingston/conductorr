# ─────────────────────────────────────────────
#  features/hand_features.py
#
#  Convert raw MediaPipe landmarks into a dict
#  of 7 interpretable features:
#
#     position_x  : wrist X in 0..1 (mirrored frame)
#     position_y  : wrist Y in 0..1
#     pitch       : hand tilt forward/back    (-1..+1)
#     yaw         : hand turn left/right      (-1..+1)
#     roll        : hand rotation like doorknob (-1..+1)
#     velocity    : smoothed wrist motion speed (0..1)
#     openness    : how open the hand is (0 = fist, 1 = spread)
#
#  All features are mean-zero where they can be (pitch/yaw/roll) so
#  "hand held flat and level in front of camera" gives ≈ 0 for all three.
#
#  Approach for pitch/yaw/roll (the "simple, based on wrist direction
#  vectors" approach):
#
#     We define two vectors in the hand plane:
#        UP      = vector from wrist (0) to middle MCP (9)
#        ACROSS  = vector from index MCP (5) to pinky MCP (17)
#
#     These two vectors span the palm. Their cross product gives a
#     PALM NORMAL vector pointing out of the palm.
#
#     - YAW    : angle of UP projected onto the XY (screen) plane,
#                relative to pure vertical.
#     - ROLL   : angle between the ACROSS vector and horizontal in
#                the XY plane.
#     - PITCH  : how much the palm normal points TOWARD/AWAY from
#                the camera (the Z component of the normalised normal).
#
#  Z coordinates from MediaPipe are relative and noisy but are
#  sufficient for pitch as a proxy — we only need a monotonic signal.
# ─────────────────────────────────────────────

import math
import numpy as np
from typing import Optional
from vision.tracker import Landmarks, HandTracker


# All feature names. Order is fixed so the UI/mapping can iterate deterministically.
FEATURE_NAMES = [
    "position_x",
    "position_y",
    "pitch",
    "yaw",
    "roll",
    "velocity",
    "openness",
]


class HandFeatureExtractor:
    """Stateful because velocity needs the previous frame's position."""

    def __init__(self):
        self._prev_xy: Optional[np.ndarray] = None

    def extract(self, lms: Optional[Landmarks]) -> Optional[dict]:
        """
        Returns a feature dict or None if no hand was detected.
        All values are in their documented ranges.
        """
        if lms is None:
            self._prev_xy = None
            return None

        pts = lms.points

        wrist = pts[HandTracker.WRIST]
        mid_mcp = pts[HandTracker.MIDDLE_MCP]
        idx_mcp = pts[HandTracker.INDEX_MCP]
        pnk_mcp = pts[HandTracker.PINKY_MCP]

        # ── Position ──
        position_x = float(wrist[0])
        position_y = float(wrist[1])

        # ── Hand size (for scale-invariant position-velocity only) ──
        # Distance wrist -> middle MCP in screen coords
        hand_size = float(np.linalg.norm(mid_mcp[:2] - wrist[:2])) + 1e-6

        # ── Openness (finger-curl angle-based) ──
        # Old approach (fingertip distance / hand size) confused tilt with
        # curl because both shrink the 2D projection.
        #
        # New approach: measure the angle at each finger's PIP joint
        # (middle knuckle). When a finger is straight, the vectors
        #    MCP -> PIP  and  PIP -> TIP
        # are nearly parallel (angle ≈ 180°). When curled into a fist,
        # they bend (angle ≈ 60–90°).
        #
        # Angles are invariant under hand rotation, so tilting the palm
        # doesn't change this signal.
        #
        # We skip the thumb — its geometry is different (saddle joint,
        # moves sideways) and including it makes "fist" ambiguous.
        #
        # MediaPipe indices per finger (MCP → PIP → TIP):
        #   index:  5  →  6  →  8
        #   middle: 9  → 10  → 12
        #   ring:  13  → 14  → 16
        #   pinky: 17  → 18  → 20
        FINGER_JOINTS = [(5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]
        angles = []
        for mcp_i, pip_i, tip_i in FINGER_JOINTS:
            v1 = pts[pip_i][:2] - pts[mcp_i][:2]
            v2 = pts[tip_i][:2] - pts[pip_i][:2]
            n1 = float(np.linalg.norm(v1)) + 1e-6
            n2 = float(np.linalg.norm(v2)) + 1e-6
            cos_a = float(np.dot(v1, v2)) / (n1 * n2)
            cos_a = max(-1.0, min(1.0, cos_a))
            angles.append(math.acos(cos_a))   # radians; 0 = straight, π/2 = fully bent

        avg_bend = sum(angles) / len(angles)   # radians
        # When open, angles ≈ 0.2 rad. When curled into a fist, angles ≈ 1.8 rad.
        # Map empirically: openness = 1 when avg_bend ≤ 0.3, = 0 when avg_bend ≥ 1.6
        # Invert so open hand = 1, fist = 0.
        openness = _clamp01(1.0 - (avg_bend - 0.3) / (1.6 - 0.3))

        # ── UP vector (wrist -> middle MCP), in screen plane ──
        up = mid_mcp - wrist
        up_xy = up[:2]
        up_xy_norm = np.linalg.norm(up_xy) + 1e-6

        # Yaw: angle of UP from vertical in the screen plane.
        # "Pointing straight up" = yaw 0. Leaning to the viewer's right = +1.
        # up[0] = x component; up[1] negative because Y grows downwards.
        # atan2(dx, -dy) gives 0 when pointing straight up, positive when right.
        yaw_angle = math.atan2(up_xy[0], -up_xy[1])
        # Remap from radians in roughly [-1.2, 1.2] to [-1, 1]
        yaw = _clamp11(yaw_angle / (math.pi / 2.0))

        # ── ACROSS vector (index MCP -> pinky MCP) ──
        across = pnk_mcp - idx_mcp
        across_xy = across[:2]

        # Roll: how tilted ACROSS is from horizontal.
        # atan2(dy, dx) — 0 when horizontal, positive when pinky below index.
        # We negate dy because of image coordinates (Y grows down).
        roll_angle = math.atan2(-across_xy[1], across_xy[0])
        # When hand is palm-flat facing camera, across goes from left to right.
        # For a RIGHT hand, "pinky on right, index on left" → across_x > 0.
        # For a LEFT hand, it's the opposite. We don't care which hand; the
        # sign of roll just flips, which is a mapping choice later.
        roll = _clamp11(roll_angle / (math.pi / 2.0))

        # ── Pitch (palm normal Z component) ──
        # Compute the 3D cross product of up and across to get palm normal.
        normal = np.cross(up, across)
        norm_mag = np.linalg.norm(normal) + 1e-6
        normal /= norm_mag
        # Z component: +1 if palm faces the camera, -1 if it faces away
        # (MediaPipe's Z convention: negative Z points toward the camera, so
        # flip sign so that "palm toward camera" → positive pitch).
        pitch = _clamp11(-float(normal[2]) * 2.5)  # scale to make it reach ±1 in practice

        # ── Velocity ──
        current_xy = np.array([position_x, position_y], dtype=np.float32)
        if self._prev_xy is None:
            velocity = 0.0
        else:
            # Pixel-normalised speed: distance per frame
            dist = float(np.linalg.norm(current_xy - self._prev_xy))
            # Remap: 0.1 per-frame movement (quite fast) → 1.0
            velocity = _clamp01(dist / 0.1)
        self._prev_xy = current_xy

        return {
            "position_x": position_x,
            "position_y": position_y,
            "pitch":      pitch,
            "yaw":        yaw,
            "roll":       roll,
            "velocity":   velocity,
            "openness":   openness,
        }


# ── Helpers ────────────────────────────────

def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _clamp11(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


# ── Multi-hand extractor ──────────────────

class MultiHandExtractor:
    """
    Runs a per-hand HandFeatureExtractor for each of "left" and "right".

    Input  : dict {"left": Landmarks, "right": Landmarks}   (either may be missing)
    Output : dict {"left": features_dict | None,
                   "right": features_dict | None}
    """

    def __init__(self):
        from vision.tracker import HAND_LEFT, HAND_RIGHT, HANDS
        self._hands_order = list(HANDS)
        self._extractors = {h: HandFeatureExtractor() for h in HANDS}

    def extract(self, hands_dict: dict) -> dict:
        out = {}
        for hand in self._hands_order:
            lms = hands_dict.get(hand) if hands_dict else None
            out[hand] = self._extractors[hand].extract(lms)
        return out
