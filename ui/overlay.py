# ─────────────────────────────────────────────
#  ui/overlay.py
#
#  Live HUD: draws the current hand-features
#  panel, the resolved musical-state panel, and
#  a pulsing beat indicator.
# ─────────────────────────────────────────────

import cv2
import numpy as np

import config
from features.hand_features import FEATURE_NAMES


HUD_COLOUR    = (240, 240, 240)
OK_COLOUR     = (120, 230, 120)
WARN_COLOUR   = (60,  210, 240)
ACCENT_COLOUR = (90,  220, 255)
DIM_COLOUR    = (140, 140, 140)
BEAT_ACTIVE   = (90,  220, 255)
BEAT_IDLE     = (60,  60,  60)


def put_text(img, text, xy, scale=0.55, colour=HUD_COLOUR,
             thickness=1, shadow=True):
    x, y = xy
    if shadow:
        cv2.putText(img, text, (x + 1, y + 1),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                    thickness + 1, cv2.LINE_AA)
    cv2.putText(img, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, colour,
                thickness, cv2.LINE_AA)


def alpha_panel(img, x1, y1, x2, y2, alpha=0.55, colour=(0, 0, 0)):
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(img.shape[1], x2); y2 = min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    sub = img[y1:y2, x1:x2]
    overlay = np.full_like(sub, colour, dtype=np.uint8)
    cv2.addWeighted(overlay, alpha, sub, 1 - alpha, 0, sub)


def _bar(img, x, y, w, h, value, colour=ACCENT_COLOUR, bg=(40, 40, 40),
         centered=False):
    """Horizontal bar. value in [0,1] (or [-1,1] if centered)."""
    cv2.rectangle(img, (x, y), (x + w, y + h), bg, -1)
    if centered:
        # Bar grows from middle
        cx = x + w // 2
        half = w // 2
        v = max(-1.0, min(1.0, float(value)))
        fill = int(abs(v) * half)
        if v >= 0:
            cv2.rectangle(img, (cx, y), (cx + fill, y + h), colour, -1)
        else:
            cv2.rectangle(img, (cx - fill, y), (cx, y + h), colour, -1)
        # Center tick
        cv2.line(img, (cx, y), (cx, y + h), (90, 90, 90), 1)
    else:
        v = max(0.0, min(1.0, float(value)))
        fill = int(v * w)
        cv2.rectangle(img, (x, y), (x + fill, y + h), colour, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), (90, 90, 90), 1)


# ── Panels ──────────────────────────────────

def draw_features_panel(frame, features: dict | None,
                        x0: int = 12, y0: int = 12,
                        title: str = "FEATURES"):
    """Feature panel. Configurable position + title so we can draw one
    per hand."""
    w = 260
    h = 200
    alpha_panel(frame, x0, y0, x0 + w, y0 + h, alpha=0.55)
    put_text(frame, title, (x0 + 10, y0 + 24),
             scale=0.6, colour=ACCENT_COLOUR, thickness=2)

    if features is None:
        put_text(frame, "no hand detected",
                 (x0 + 10, y0 + 52), colour=WARN_COLOUR)
        return

    y = y0 + 46
    for name in FEATURE_NAMES:
        v = features.get(name, 0.0)
        put_text(frame, f"{name:10s}", (x0 + 10, y),
                 scale=0.42, colour=DIM_COLOUR)
        put_text(frame, f"{v:+.2f}", (x0 + 95, y),
                 scale=0.42, colour=HUD_COLOUR)
        centered = name in ("pitch", "yaw", "roll")
        _bar(frame, x0 + 140, y - 10, 110, 10, v, centered=centered)
        y += 20


def draw_both_feature_panels(frame, per_hand: dict):
    """Draw a panel for each hand, stacked on the left side of the screen."""
    left_feats = per_hand.get("left") if per_hand else None
    right_feats = per_hand.get("right") if per_hand else None
    draw_features_panel(frame, left_feats,
                        x0=12, y0=12, title="LEFT HAND")
    draw_features_panel(frame, right_feats,
                        x0=12, y0=222, title="RIGHT HAND")


def draw_music_panel(frame, resolved: dict, arp_snapshot: dict, bpm: float):
    """Top-right panel showing current musical state."""
    fw = frame.shape[1]
    w = 260
    x0 = fw - w - 12
    y0 = 12
    h = 220
    alpha_panel(frame, x0, y0, x0 + w, y0 + h, alpha=0.55)

    put_text(frame, "MUSIC", (x0 + 10, y0 + 24),
             scale=0.6, colour=ACCENT_COLOUR, thickness=2)

    lines = [
        ("chord",      resolved.get("chord_name", "?")),
        ("complexity", resolved.get("complexity", "triad")),
        ("octave",     f"{int(round(resolved.get('octave', 0)))}"),
        ("tempo",      f"{int(round(bpm))} BPM"),
        ("pattern",    resolved.get("pattern", "?")),
        ("gate",       f"{resolved.get('gate', 0.0):.2f}"),
        ("velocity",   f"{int(round(resolved.get('velocity', 0)))}"),
        ("mode",       resolved.get("mode", "?").upper()),
    ]
    y = y0 + 46
    for label, val in lines:
        put_text(frame, f"{label:10s}", (x0 + 10, y),
                 scale=0.45, colour=DIM_COLOUR)
        colour = OK_COLOUR if label == "mode" and val == "ARP" else HUD_COLOUR
        put_text(frame, str(val), (x0 + 105, y),
                 scale=0.5, colour=colour)
        y += 20


def draw_beat_indicator(frame, step_number: int, subdivision: int = config.SUBDIVISION):
    """Bottom-center: 4 dots showing position within the bar."""
    fh = frame.shape[0]
    fw = frame.shape[1]
    beats_per_bar = 4
    steps_per_beat = subdivision
    total_steps = beats_per_bar * steps_per_beat
    pos_in_bar = step_number % total_steps
    current_beat = pos_in_bar // steps_per_beat

    cx = fw // 2
    cy = fh - 40
    radius = 10
    spacing = 36

    for b in range(beats_per_bar):
        x = cx - (beats_per_bar - 1) * spacing // 2 + b * spacing
        colour = BEAT_ACTIVE if b == current_beat else BEAT_IDLE
        r = radius + 4 if b == current_beat else radius
        cv2.circle(frame, (x, cy), r, colour, -1)
        cv2.circle(frame, (x, cy), r, (20, 20, 20), 1)


def draw_footer(frame, midi_port: str):
    """Bottom-left: MIDI port name + hint."""
    fh = frame.shape[0]
    put_text(frame, f"MIDI: {midi_port}",
             (12, fh - 14),
             scale=0.45, colour=DIM_COLOUR)

    put_text(frame, "Q/ESC = quit",
             (frame.shape[1] - 130, fh - 14),
             scale=0.45, colour=DIM_COLOUR)
