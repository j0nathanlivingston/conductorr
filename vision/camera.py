# ─────────────────────────────────────────────
#  vision/camera.py
#  Opens the webcam. Fails clearly if it can't.
# ─────────────────────────────────────────────

import sys
import cv2
import config


def open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        print(
            f"[ERROR] Cannot open camera at index {config.CAMERA_INDEX}.\n"
            "Try another index (0, 1, 2...) in config.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    return cap
