# ─────────────────────────────────────────────
# ui/control_menu.py
#
# Clickable control menu with dropdowns.
#
# Layout per row:
#   [  Parameter name  ]  [  Binding cell (click to open dropdown)  ]  [ X ]
#
# Click a binding cell → a dropdown overlay appears listing every
# possible binding (OFF + each hand × feature). Click one to set it.
# Click the "X" to set the binding to OFF.
# Click outside the dropdown to close it without changing.
#
# Keyboard shortcuts are kept for power-users:
#   J / K  : move selection down / up
#   H / L  : cycle selected binding backward / forward
#   X      : toggle OFF / restore default
#   R      : reset all to defaults
# ─────────────────────────────────────────────

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List

from mapping.control_router import (
    ControlRouter,
    PARAM_ORDER, PARAM_LABELS,
    BINDING_ORDER, binding_label,
    HANDS, FEATURE_NAMES, FEATURE_LABELS, HAND_LABELS,
)

WINDOW_NAME = "Control Menu"

# Canvas dimensions
WIDTH   = 760
HEIGHT  = 1040

# Layout constants
MARGIN_X      = 24
MODE_TOGGLE_Y = 80       # big MIDI/MAC toggle button
MODE_TOGGLE_H = 50
ROW_START_Y   = 320
ROW_HEIGHT    = 36
PARAM_COL_W   = 230
BINDING_COL_W = 320
OFF_COL_W     = 60
BINDING_COL_X = MARGIN_X + PARAM_COL_W
OFF_COL_X     = BINDING_COL_X + BINDING_COL_W + 16

# Dropdown layout
DD_ROW_H      = 28
DD_WIDTH      = BINDING_COL_W
DD_MAX_VISIBLE = 18   # fits fine — BINDING_ORDER is 15 items


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


# Module-level state because OpenCV callbacks don't play well with closures
# and we want the menu to be self-contained. Owned by ControlMenu below.

class ControlMenu:
    """
    Drawable + interactive menu. Own an instance of this and call:

        menu = ControlMenu(router)
        menu.handle_mouse(event, x, y)          # from mouse callback
        menu.handle_key(key)                    # returns True if consumed
        frame = menu.draw()
    """

    def __init__(self, router: ControlRouter, on_mode_change=None):
        """
        router: ControlRouter instance
        on_mode_change: optional callable(new_mode: str) called when the user
                        clicks the mode toggle button. Used by main.py to
                        panic notes when switching into Mac mode.
        """
        self.router = router
        self.on_mode_change = on_mode_change
        self._row_rects: List[Tuple[str, Rect, Rect]] = []
        # (param, binding_rect, off_rect) per row

        # Mode-toggle button rect (populated by draw())
        self._mode_rect: Optional[Rect] = None

        # Dropdown state
        self._dd_open_param: Optional[str] = None
        self._dd_rect: Optional[Rect] = None
        self._dd_option_rects: List[Tuple[Rect, Optional[Tuple[str, str]]]] = []

        # Hover state — for the binding and off columns
        self._mouse_xy: Tuple[int, int] = (-1, -1)

    # ── Input ────────────────────────────────

    def handle_mouse(self, event, x, y):
        self._mouse_xy = (x, y)

        if event != cv2.EVENT_LBUTTONDOWN:
            return

        # If dropdown is open, check it first
        if self._dd_open_param is not None and self._dd_rect is not None:
            # Click an option?
            for rect, binding in self._dd_option_rects:
                if rect.contains(x, y):
                    self.router.set_binding(self._dd_open_param, binding)
                    self._dd_open_param = None
                    self._dd_rect = None
                    self._dd_option_rects = []
                    return
            # Click outside the dropdown → close it
            self._dd_open_param = None
            self._dd_rect = None
            self._dd_option_rects = []
            return

        # Mode toggle?
        if self._mode_rect is not None and self._mode_rect.contains(x, y):
            new_mode = self.router.toggle_mode()
            if self.on_mode_change is not None:
                try:
                    self.on_mode_change(new_mode)
                except Exception as e:
                    print(f"[menu] on_mode_change callback failed: {e}")
            return

        # Otherwise check rows
        for param, binding_rect, off_rect in self._row_rects:
            if binding_rect.contains(x, y):
                # Select this row + open its dropdown
                self.router.select_param(param)
                self._open_dropdown(param, binding_rect)
                return
            if off_rect.contains(x, y):
                self.router.select_param(param)
                self.router.set_binding(param, None)
                return

    def handle_key(self, key) -> bool:
        """Keyboard shortcuts. Returns True if the key was consumed."""
        if key in (ord("j"), ord("J")):
            self._close_dropdown()
            self.router.move_selection(+1)
            return True
        if key in (ord("k"), ord("K")):
            self._close_dropdown()
            self.router.move_selection(-1)
            return True
        if key in (ord("l"), ord("L")):
            self.router.cycle_binding(self.router.selected_param(), +1)
            return True
        if key in (ord("h"), ord("H")):
            self.router.cycle_binding(self.router.selected_param(), -1)
            return True
        if key in (ord("x"), ord("X")):
            self.router.toggle_off_or_default(self.router.selected_param())
            return True
        if key in (ord("r"), ord("R")):
            self.router.reset_defaults()
            self._close_dropdown()
            return True
        return False

    def _open_dropdown(self, param: str, anchor_rect: Rect):
        # Position dropdown just below the anchor, clipped to canvas
        items = BINDING_ORDER
        dd_h = min(DD_MAX_VISIBLE, len(items)) * DD_ROW_H + 6

        dd_y = anchor_rect.y + anchor_rect.h + 2
        if dd_y + dd_h > HEIGHT - 10:
            # Flip upward instead
            dd_y = max(10, anchor_rect.y - dd_h - 2)

        self._dd_rect = Rect(anchor_rect.x, dd_y, DD_WIDTH, dd_h)
        self._dd_open_param = param

        # Compute option rects
        self._dd_option_rects = []
        for i, binding in enumerate(items):
            r = Rect(
                self._dd_rect.x + 3,
                self._dd_rect.y + 3 + i * DD_ROW_H,
                DD_WIDTH - 6,
                DD_ROW_H,
            )
            self._dd_option_rects.append((r, binding))

    def _close_dropdown(self):
        self._dd_open_param = None
        self._dd_rect = None
        self._dd_option_rects = []

    # ── Drawing ──────────────────────────────

    def draw(self) -> np.ndarray:
        canvas = np.full((HEIGHT, WIDTH, 3), 22, dtype=np.uint8)

        # Title
        cv2.putText(canvas, "Control Menu",
                    (MARGIN_X, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(canvas,
                    "Click a binding to change it, click X to disable",
                    (MARGIN_X, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (180, 180, 180), 1)

        # ── Mode toggle button ──
        mode = getattr(self.router, "mode", "midi")
        mode_rect = Rect(MARGIN_X, MODE_TOGGLE_Y,
                         WIDTH - 2 * MARGIN_X, MODE_TOGGLE_H)
        self._mode_rect = mode_rect

        mx, my = self._mouse_xy
        hovered = mode_rect.contains(mx, my)

        if mode == "midi":
            bg = (55, 95, 55) if hovered else (40, 75, 40)
            border = (110, 200, 110)
            label = "MODE: MIDI  →  click to switch to Mac Controller"
        else:
            bg = (95, 55, 55) if hovered else (75, 40, 40)
            border = (200, 110, 110)
            label = "MODE: MAC CONTROLLER  →  click to switch to MIDI"

        cv2.rectangle(canvas,
                      (mode_rect.x, mode_rect.y),
                      (mode_rect.x + mode_rect.w, mode_rect.y + mode_rect.h),
                      bg, -1)
        cv2.rectangle(canvas,
                      (mode_rect.x, mode_rect.y),
                      (mode_rect.x + mode_rect.w, mode_rect.y + mode_rect.h),
                      border, 2)
        cv2.putText(canvas, label,
                    (mode_rect.x + 16, mode_rect.y + 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (245, 245, 245), 2)

        # ── Keyboard shortcuts box ──
        kb_y = MODE_TOGGLE_Y + MODE_TOGGLE_H + 15
        kb_h = 110
        cv2.rectangle(canvas, (MARGIN_X - 2, kb_y),
                      (WIDTH - MARGIN_X + 2, kb_y + kb_h),
                      (40, 40, 40), -1)
        cv2.rectangle(canvas, (MARGIN_X - 2, kb_y),
                      (WIDTH - MARGIN_X + 2, kb_y + kb_h),
                      (70, 70, 70), 1)
        lines = [
            "J / K   move selection down / up",
            "H / L   cycle binding backward / forward",
            "X       disable / restore default",
            "R       reset all to defaults",
            "Q / ESC quit",
        ]
        for i, ln in enumerate(lines):
            cv2.putText(canvas, ln,
                        (MARGIN_X + 6, kb_y + 20 + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.47, (215, 215, 215), 1)

        # Column headers
        hdr_y = ROW_START_Y - 16
        cv2.putText(canvas, "Function", (MARGIN_X, hdr_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1)
        cv2.putText(canvas, "Gesture binding", (BINDING_COL_X, hdr_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1)
        cv2.putText(canvas, "OFF", (OFF_COL_X, hdr_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1)

        # Divider line
        cv2.line(canvas, (MARGIN_X, hdr_y + 6),
                 (WIDTH - MARGIN_X, hdr_y + 6), (70, 70, 70), 1)

        # Rows
        self._row_rects = []
        selected_param = self.router.selected_param()
        mx, my = self._mouse_xy

        for idx, param in enumerate(PARAM_ORDER):
            y = ROW_START_Y + idx * ROW_HEIGHT
            selected = (param == selected_param)
            binding = self.router.get_binding(param)
            is_off = binding is None

            # Visual divider between arpeggiator group and MIDI group
            if param == "midi_volume":
                cv2.line(canvas, (MARGIN_X, y - 8),
                         (WIDTH - MARGIN_X, y - 8), (60, 60, 60), 1)
                cv2.putText(canvas, "MIDI subgroup",
                            (MARGIN_X, y - 11),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 140, 140), 1)
            if param == "midi_cutoff":
                cv2.line(canvas, (MARGIN_X, y - 8),
                         (WIDTH - MARGIN_X, y - 8), (60, 60, 60), 1)
                cv2.putText(canvas, "Extra CCs",
                            (MARGIN_X, y - 11),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 140, 140), 1)

            # Selection highlight (very subtle)
            if selected:
                cv2.rectangle(canvas,
                              (MARGIN_X - 4, y - 4),
                              (WIDTH - MARGIN_X + 4, y + 26),
                              (45, 55, 85), -1)

            # Param label
            cv2.putText(canvas, PARAM_LABELS.get(param, param),
                        (MARGIN_X, y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.54,
                        (245, 245, 245) if not is_off else (160, 160, 160), 1)

            # Binding cell — clickable
            binding_rect = Rect(BINDING_COL_X, y - 2, BINDING_COL_W, 28)
            hovered = binding_rect.contains(mx, my)
            cell_bg = (60, 70, 95) if hovered else (50, 50, 50)
            if is_off:
                cell_bg = (55, 40, 40)
            cv2.rectangle(canvas,
                          (binding_rect.x, binding_rect.y),
                          (binding_rect.x + binding_rect.w,
                           binding_rect.y + binding_rect.h),
                          cell_bg, -1)
            cv2.rectangle(canvas,
                          (binding_rect.x, binding_rect.y),
                          (binding_rect.x + binding_rect.w,
                           binding_rect.y + binding_rect.h),
                          (95, 95, 95) if not hovered else (140, 170, 220), 1)

            lbl = binding_label(binding)
            cv2.putText(canvas, lbl,
                        (binding_rect.x + 8, binding_rect.y + 19),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        (80, 80, 220) if is_off else (230, 230, 230),
                        1 if is_off else 2 if hovered else 1)
            # Dropdown arrow glyph
            ax = binding_rect.x + binding_rect.w - 18
            ay = binding_rect.y + binding_rect.h // 2
            pts = np.array([
                [ax,     ay - 4],
                [ax + 10, ay - 4],
                [ax + 5, ay + 4],
            ], dtype=np.int32)
            cv2.fillPoly(canvas, [pts], (200, 200, 200))

            # OFF button
            off_rect = Rect(OFF_COL_X, y - 2, OFF_COL_W, 28)
            off_hovered = off_rect.contains(mx, my)
            off_bg = (70, 45, 45) if off_hovered else (45, 35, 35)
            cv2.rectangle(canvas,
                          (off_rect.x, off_rect.y),
                          (off_rect.x + off_rect.w, off_rect.y + off_rect.h),
                          off_bg, -1)
            cv2.rectangle(canvas,
                          (off_rect.x, off_rect.y),
                          (off_rect.x + off_rect.w, off_rect.y + off_rect.h),
                          (150, 80, 80) if off_hovered else (90, 60, 60), 1)
            cv2.putText(canvas, "X",
                        (off_rect.x + 21, off_rect.y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (240, 120, 120), 2)

            self._row_rects.append((param, binding_rect, off_rect))

        # Footer
        footer_y = HEIGHT - 58
        cv2.putText(canvas,
                    "Two-hand support: L = left hand, R = right hand",
                    (MARGIN_X, footer_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        cv2.putText(canvas,
                    "Mac mode gestures: swipe L/R = spaces, hold open = Mission Ctrl,",
                    (MARGIN_X, footer_y + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1)
        cv2.putText(canvas,
                    "hold fist = show desktop, hand Y = volume, hand X = brightness",
                    (MARGIN_X, footer_y + 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1)

        # Dropdown (drawn LAST so it's on top)
        if self._dd_open_param is not None and self._dd_rect is not None:
            self._draw_dropdown(canvas)

        return canvas

    def _draw_dropdown(self, canvas):
        r = self._dd_rect
        cv2.rectangle(canvas, (r.x, r.y), (r.x + r.w, r.y + r.h),
                      (30, 30, 35), -1)
        cv2.rectangle(canvas, (r.x, r.y), (r.x + r.w, r.y + r.h),
                      (160, 170, 200), 2)

        mx, my = self._mouse_xy
        current_binding = self.router.get_binding(self._dd_open_param)

        for opt_rect, binding in self._dd_option_rects:
            hovered = opt_rect.contains(mx, my)
            is_current = (binding == current_binding)
            if hovered:
                cv2.rectangle(canvas,
                              (opt_rect.x, opt_rect.y),
                              (opt_rect.x + opt_rect.w,
                               opt_rect.y + opt_rect.h),
                              (70, 90, 130), -1)
            elif is_current:
                cv2.rectangle(canvas,
                              (opt_rect.x, opt_rect.y),
                              (opt_rect.x + opt_rect.w,
                               opt_rect.y + opt_rect.h),
                              (45, 55, 80), -1)

            lbl = binding_label(binding)
            text_colour = (240, 240, 240)
            if binding is None:
                text_colour = (210, 130, 130)
            cv2.putText(canvas, lbl,
                        (opt_rect.x + 10, opt_rect.y + 19),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, text_colour,
                        2 if is_current else 1)


# ── Legacy shim so main.py's existing imports still work ──
# main.py does:
#   from ui.control_menu import draw_control_menu, handle_menu_key, WINDOW_NAME
# We keep those function names available but they need a ControlMenu
# instance. To avoid forcing a big rewrite of main.py, these shims are
# module-level and take the router; main.py will be updated to use
# ControlMenu directly.

def draw_control_menu(router: ControlRouter):
    """Deprecated: construct a ControlMenu and call .draw() instead."""
    menu = ControlMenu(router)
    return menu.draw()


def handle_menu_key(key: int, router: ControlRouter) -> bool:
    """Deprecated: use ControlMenu.handle_key() instead."""
    menu = ControlMenu(router)
    return menu.handle_key(key)
