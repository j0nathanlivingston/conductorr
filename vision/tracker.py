# ─────────────────────────────────────────────
#  vision/tracker.py
#
#  Wraps MediaPipe Hands. Tracks up to TWO hands
#  and labels each as "left" or "right" from the
#  user's point of view (not the camera's).
#
#  Mirror-flip handling:
#    main.py flips the frame BEFORE calling us,
#    so MediaPipe processes the mirrored frame.
#    MediaPipe's handedness classifier assumes a
#    non-mirrored view of the WORLD, so when the
#    input is mirrored, its "Left" label actually
#    corresponds to the user's right hand. We
#    compensate by inverting the label when
#    MIRROR_CAMERA is True.
#
#    This mirrors the real-world naming that the
#    user expects: "left" in our dict = the hand
#    on the left side of what the user sees on
#    screen (which IS the user's own right hand
#    from their body's point of view, but that's
#    the mirror convention everyone uses).
# ─────────────────────────────────────────────

import sys
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict
import config


_MP_FIX_MSG = (
    "\n[ERROR] MediaPipe missing the classic `solutions` API.\n"
    "Fix:\n"
    "   pip uninstall mediapipe mediapipe-silicon -y\n"
    "   pip install 'mediapipe==0.10.14'\n"
)

try:
    import mediapipe as mp
    _ = mp.solutions.hands.Hands
    _ = mp.solutions.drawing_utils
    _ = mp.solutions.drawing_styles
except (ImportError, AttributeError) as e:
    print(_MP_FIX_MSG + f"(original error: {e})\n", file=sys.stderr)
    raise


@dataclass
class Landmarks:
    """21 landmarks with x, y, z each normalised (x, y in 0..1).
    If mirror_applied is True, the x coordinates have been flipped so they
    match the user's mirrored view."""
    points: np.ndarray   # shape (21, 3), dtype float32
    mirror_applied: bool = False

    def point(self, idx: int) -> np.ndarray:
        return self.points[idx]


# Hand identifiers — pinning these to literal strings so the rest of the
# app has one canonical vocabulary.
HAND_LEFT = "left"
HAND_RIGHT = "right"
HANDS = (HAND_LEFT, HAND_RIGHT)


class HandTracker:
    """
    Tracks up to two hands. Call process(bgr_frame) each frame; returns
    (hands_dict, annotated_frame).

    hands_dict maps "left" / "right" → Landmarks, with one or both entries
    possibly missing if the corresponding hand isn't visible.
    """

    # Landmark index reference (MediaPipe convention)
    WRIST = 0
    INDEX_MCP = 5
    MIDDLE_MCP = 9
    RING_MCP = 13
    PINKY_MCP = 17
    FINGERTIPS = [4, 8, 12, 16, 20]

    def __init__(self):
        self._mp_hands = mp.solutions.hands
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_style = mp.solutions.drawing_styles
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=config.MP_MODEL_COMPLEXITY,
            min_detection_confidence=config.MP_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=config.MP_MIN_TRACKING_CONFIDENCE,
        )

    def process(self, bgr_frame: np.ndarray):
        """
        Returns (hands_dict, annotated_frame).
        hands_dict: {"left": Landmarks, "right": Landmarks} (either may be
        missing).
        """
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._hands.process(rgb)
        annotated = bgr_frame.copy()

        hands: Dict[str, Landmarks] = {}
        if not result.multi_hand_landmarks:
            return hands, annotated

        for i, hand_lms in enumerate(result.multi_hand_landmarks):
            # Handedness: MediaPipe returns a classification with
            # label "Left" / "Right" relative to the ORIGINAL camera frame.
            label = "Right"
            if (result.multi_handedness is not None
                    and i < len(result.multi_handedness)):
                try:
                    label = result.multi_handedness[i].classification[0].label
                except Exception:
                    pass

            # IMPORTANT — mirror-aware handedness mapping.
            #
            # main.py horizontally flips the frame BEFORE calling us,
            # so MediaPipe processes the mirrored image. When the input
            # is already mirrored, MediaPipe's "Left" label now
            # corresponds to the hand on the left side of the user's
            # view, and "Right" to the right side. (In other words,
            # MediaPipe's model internally un-mirrors, but since the
            # input was already mirrored, the labels end up correct
            # from the user's perspective — no flip needed.)
            #
            # Previous version of this code inverted the labels, which
            # is why the on-screen "L" and "R" looked backwards.
            if label == "Left":
                hand_key = HAND_LEFT
            else:
                hand_key = HAND_RIGHT

            # Build numpy landmark array — the incoming frame was already
            # flipped by main.py, so landmarks are already in user-view space.
            pts = np.array(
                [[lm.x, lm.y, lm.z] for lm in hand_lms.landmark],
                dtype=np.float32,
            )

            # If both hands get the same label (rare MediaPipe bug), the
            # second one wins — we disambiguate by X-position instead:
            # whichever hand has smaller x is "left".
            if hand_key in hands:
                # Compare by wrist x
                existing_x = float(hands[hand_key].points[0, 0])
                new_x = float(pts[0, 0])
                if new_x < existing_x:
                    # New one is more to the left → put new in LEFT, old in RIGHT
                    hands[HAND_RIGHT] = hands[hand_key]
                    hand_key = HAND_LEFT
                else:
                    hand_key = HAND_RIGHT

            hands[hand_key] = Landmarks(points=pts, mirror_applied=config.MIRROR_CAMERA)

            # Draw skeleton on the annotated frame (which is the already-
            # flipped frame that was passed in).
            if config.SHOW_LANDMARKS:
                self._mp_draw.draw_landmarks(
                    annotated, hand_lms, self._mp_hands.HAND_CONNECTIONS,
                    self._mp_style.get_default_hand_landmarks_style(),
                    self._mp_style.get_default_hand_connections_style(),
                )

        return hands, annotated

    def close(self):
        self._hands.close()
