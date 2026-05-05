# ─────────────────────────────────────────────
# mac/controller.py
#
# Turns hand gestures into macOS actions:
#
#   swipe LEFT     →  previous space (Ctrl+←)
#   swipe RIGHT    →  next space     (Ctrl+→)
#   open palm held →  Mission Control (Ctrl+↑)
#   fist held      →  show desktop   (F11)
#   hand Y         →  system volume  (continuous)
#   hand X         →  brightness     (continuous, with Shift+Fn+F1/F2 fallback)
#
# All actions are dispatched via `osascript`. The first time any
# keyboard-synthesis action fires, macOS will prompt for Accessibility
# permission for the running terminal / Python process. Grant it in
# System Settings → Privacy & Security → Accessibility.
#
# This module is a no-op on non-macOS platforms — its public API still
# works but all methods return immediately.
#
# Thread-model: only used from the main thread. Not thread-safe.
# ─────────────────────────────────────────────

import platform
import subprocess
import time
from collections import deque
from typing import Optional, Tuple


IS_MACOS = platform.system() == "Darwin"


# Tunable thresholds — edit these to adjust the feel
SWIPE_WINDOW_SEC      = 0.40    # rolling window for swipe detection
SWIPE_MIN_DELTA_X     = 0.30    # how much x must change within the window (in 0..1 screen-normalised units)
SWIPE_COOLDOWN_SEC    = 0.70    # minimum time between consecutive swipes

STATIC_POSE_SEC       = 0.60    # hold a pose this long before it fires
STATIC_VELOCITY_MAX   = 0.08    # hand must be moving slower than this to count as "still"

FIST_OPENNESS         = 0.20    # openness below this = fist
OPEN_OPENNESS         = 0.75    # openness above this = open palm

VOLUME_FEATURE        = "position_y"    # which feature controls volume (lower is louder)
VOLUME_MIN_DELTA      = 0.04    # only send volume update if value changed by this much

BRIGHTNESS_FEATURE    = "position_x"
BRIGHTNESS_MIN_DELTA  = 0.05


def _osa(script: str) -> bool:
    """Run an AppleScript fragment. Returns True on success."""
    if not IS_MACOS:
        return False
    try:
        subprocess.run(["osascript", "-e", script],
                       check=False, capture_output=True, timeout=1.0)
        return True
    except Exception:
        return False


def _key_code(code: int, modifiers: Optional[list] = None) -> bool:
    """Synthesize a key press. modifiers is a list like ['control down']."""
    if modifiers:
        mod_str = ", ".join(modifiers)
        script = f'tell application "System Events" to key code {code} using {{{mod_str}}}'
    else:
        script = f'tell application "System Events" to key code {code}'
    return _osa(script)


# macOS virtual key codes we care about
KEY_ARROW_LEFT   = 123
KEY_ARROW_RIGHT  = 124
KEY_ARROW_DOWN   = 125
KEY_ARROW_UP     = 126
KEY_F11          = 103   # show desktop (on most setups)
KEY_MISSION_CTRL = 160   # F3 / mission control


class MacController:
    """
    State machine that watches hand features and fires macOS actions.

    Call `update(per_hand_features)` every frame from main.py. It handles
    its own gesture detection, debouncing, and throttling.
    """

    def __init__(self, active_hand: str = "right"):
        """
        active_hand: which hand's features to read. "right" by default so
        the user can use their left hand to trigger the menu or rest.
        """
        self.active_hand = active_hand
        self.enabled = False

        # Swipe tracking: rolling buffer of (timestamp, x_position)
        self._x_history = deque(maxlen=30)
        self._last_swipe_time = 0.0

        # Static-pose tracking
        self._pose_started_at: Optional[float] = None
        self._pose_kind: Optional[str] = None   # "open" or "fist"
        self._pose_fired = False

        # Continuous controls — only send when the value changes meaningfully
        self._last_volume: Optional[int] = None
        self._last_brightness: Optional[int] = None

        # Status for the UI — what happened most recently
        self._last_action: str = ""
        self._last_action_time: float = 0.0

    # ── Public control ──

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._reset_state()
        if enabled:
            self._last_action = "Mac mode active"
            self._last_action_time = time.time()

    def set_active_hand(self, hand: str):
        if hand in ("left", "right"):
            self.active_hand = hand
            self._reset_state()

    def _reset_state(self):
        self._x_history.clear()
        self._pose_started_at = None
        self._pose_kind = None
        self._pose_fired = False
        # Don't reset _last_volume/_last_brightness — leaving the system
        # where it was is fine.

    # ── Per-frame ──

    def update(self, per_hand_features: Optional[dict]) -> None:
        if not self.enabled or not IS_MACOS:
            return

        feats = (per_hand_features or {}).get(self.active_hand)
        if feats is None:
            # Hand not visible — clear any ongoing pose, but keep history
            # so a brief tracking drop doesn't kill an ongoing swipe
            self._pose_started_at = None
            self._pose_kind = None
            self._pose_fired = False
            return

        now = time.time()
        x = feats.get("position_x", 0.5)
        y = feats.get("position_y", 0.5)
        openness = feats.get("openness", 0.5)
        velocity = feats.get("velocity", 0.0)

        self._detect_swipe(now, x)
        self._detect_static_pose(now, openness, velocity)
        self._update_volume(y)
        self._update_brightness(x)

    # ── Swipe detection ──

    def _detect_swipe(self, now: float, x: float):
        self._x_history.append((now, x))

        # Cooldown: ignore swipes too close to the last one
        if now - self._last_swipe_time < SWIPE_COOLDOWN_SEC:
            return

        # Drop old samples outside the rolling window
        cutoff = now - SWIPE_WINDOW_SEC
        while self._x_history and self._x_history[0][0] < cutoff:
            self._x_history.popleft()

        if len(self._x_history) < 4:
            return

        # Compute total displacement across the window
        x_start = self._x_history[0][1]
        x_end = self._x_history[-1][1]
        dx = x_end - x_start

        if dx > SWIPE_MIN_DELTA_X:
            # Swipe right
            _key_code(KEY_ARROW_RIGHT, ["control down"])
            self._fire("Swipe right → next space")
            self._last_swipe_time = now
            self._x_history.clear()
        elif dx < -SWIPE_MIN_DELTA_X:
            # Swipe left
            _key_code(KEY_ARROW_LEFT, ["control down"])
            self._fire("Swipe left → prev space")
            self._last_swipe_time = now
            self._x_history.clear()

    # ── Static-pose detection (fist / open palm held still) ──

    def _detect_static_pose(self, now: float, openness: float, velocity: float):
        # Must be still
        is_still = velocity < STATIC_VELOCITY_MAX

        if not is_still:
            self._pose_started_at = None
            self._pose_kind = None
            self._pose_fired = False
            return

        # Classify current pose
        if openness <= FIST_OPENNESS:
            current = "fist"
        elif openness >= OPEN_OPENNESS:
            current = "open"
        else:
            current = None

        if current is None:
            self._pose_started_at = None
            self._pose_kind = None
            self._pose_fired = False
            return

        # Pose changed → restart timer
        if current != self._pose_kind:
            self._pose_kind = current
            self._pose_started_at = now
            self._pose_fired = False
            return

        # Pose held — fire if we've been in it long enough and haven't fired yet
        if (not self._pose_fired
                and self._pose_started_at is not None
                and now - self._pose_started_at >= STATIC_POSE_SEC):
            if current == "open":
                _key_code(KEY_MISSION_CTRL)
                self._fire("Open palm held → Mission Control")
            elif current == "fist":
                _key_code(KEY_F11)
                self._fire("Fist held → Show Desktop")
            self._pose_fired = True

    # ── Continuous: volume ──

    def _update_volume(self, y: float):
        # y is 0 at top of screen, 1 at bottom. Invert so hand UP = volume UP.
        target = int(round((1.0 - max(0.0, min(1.0, y))) * 100))
        if (self._last_volume is None
                or abs(target - self._last_volume) >= int(VOLUME_MIN_DELTA * 100)):
            _osa(f"set volume output volume {target}")
            self._last_volume = target

    # ── Continuous: brightness ──

    def _update_brightness(self, x: float):
        # Brightness is trickier — there's no clean AppleScript for it on
        # modern macOS. We fall back to tapping F1 / F2 when the target
        # crosses big steps. This is a best-effort control, not precise.
        target_step = int(round(max(0.0, min(1.0, x)) * 16))   # 16 brightness notches
        if self._last_brightness is None:
            self._last_brightness = target_step
            return
        if target_step == self._last_brightness:
            return

        # Step in the direction of the target
        direction = 1 if target_step > self._last_brightness else -1
        steps = min(abs(target_step - self._last_brightness), 3)   # max 3 per frame
        for _ in range(steps):
            if direction > 0:
                _key_code(145)   # brightness up
            else:
                _key_code(144)   # brightness down
            self._last_brightness += direction

    # ── Status for UI ──

    def _fire(self, action: str):
        self._last_action = action
        self._last_action_time = time.time()

    def status(self) -> str:
        """Short status string for the HUD."""
        if not IS_MACOS and self.enabled:
            return "Mac mode unavailable (not on macOS)"
        if not self.enabled:
            return "MIDI mode"
        # Recent action fades after 2 seconds
        if time.time() - self._last_action_time < 2.0:
            return f"MAC: {self._last_action}"
        return f"MAC: watching {self.active_hand} hand"
