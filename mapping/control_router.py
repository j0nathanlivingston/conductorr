# ─────────────────────────────────────────────
# mapping/control_router.py
#
# Runtime gesture-to-musical-parameter router.
#
# TWO-HAND aware. Every binding is a (hand, feature)
# pair where hand is "left" or "right" and feature is
# one of the seven per-hand features. A binding of None
# means that parameter is disabled and takes its default.
#
# The control menu edits this object at runtime.
# ─────────────────────────────────────────────

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Bindings are tuples of (hand, feature) or None.
Binding = Optional[Tuple[str, str]]


# Every musical parameter the router can control.
# Grouped: arpeggiator first, then MIDI subgroup.
PARAM_ORDER = [
    # Arpeggiator / note engine
    "chord",
    "octave",
    "tempo",
    "pattern",
    "gate",
    "velocity",
    "mode",
    "complexity",
    # MIDI subgroup
    "midi_volume",
    "midi_pan",
    "midi_modulation",
    "midi_expression",
    "midi_sustain",
    "pitch_bend",
    # New: filter & reverb
    "midi_cutoff",
    "midi_resonance",
    "midi_reverb",
]


# The 7 features that live on each hand.
FEATURE_NAMES = [
    "position_x",
    "position_y",
    "pitch",
    "yaw",
    "roll",
    "velocity",
    "openness",
]

# The two hands.
HANDS = ("left", "right")


# Every possible binding option — (hand, feature) for every combination,
# plus None for "disabled". The menu cycles through this list.
BINDING_ORDER: List[Binding] = [None]
for _hand in HANDS:
    for _feat in FEATURE_NAMES:
        BINDING_ORDER.append((_hand, _feat))


# Pretty labels
PARAM_LABELS = {
    "chord":           "Chord",
    "octave":          "Octave",
    "tempo":           "Tempo",
    "pattern":         "Pattern",
    "gate":            "Gate",
    "velocity":        "Note Velocity",
    "mode":            "Mode (arp/sustain)",
    "complexity":      "Chord Complexity",
    "midi_volume":     "MIDI Volume",
    "midi_pan":        "MIDI Pan",
    "midi_modulation": "MIDI Modulation",
    "midi_expression": "MIDI Expression",
    "midi_sustain":    "MIDI Sustain",
    "pitch_bend":      "Pitch Bend",
    "midi_cutoff":     "Filter Cutoff (CC 74)",
    "midi_resonance":  "Resonance (CC 71)",
    "midi_reverb":     "Reverb Send (CC 91)",
}

FEATURE_LABELS = {
    "position_x": "Hand X",
    "position_y": "Hand Y",
    "pitch":      "Pitch / Tilt",
    "yaw":        "Yaw / Turn",
    "roll":       "Roll / Twist",
    "velocity":   "Motion Speed",
    "openness":   "Openness",
}

HAND_LABELS = {
    "left":  "L",
    "right": "R",
}


def binding_label(b: Binding) -> str:
    """Human-readable label for a binding."""
    if b is None:
        return "OFF"
    hand, feat = b
    return f"{HAND_LABELS.get(hand, hand)}: {FEATURE_LABELS.get(feat, feat)}"


# Defaults. Right hand drives the core musical controls; left hand
# provides secondary expression. "midi_volume", "midi_sustain", "pitch_bend",
# and the new filter/reverb controls start disabled so the user opts in.
DEFAULT_BINDINGS: Dict[str, Binding] = {
    "chord":           ("right", "position_x"),
    "octave":          ("right", "position_y"),
    "tempo":           ("right", "roll"),
    "pattern":         ("right", "yaw"),
    "gate":            ("right", "pitch"),
    "velocity":        ("right", "velocity"),
    "mode":            ("right", "openness"),
    "complexity":      ("left",  "openness"),   # fist = triad, spread = 9th
    "midi_volume":     None,
    "midi_pan":        ("left",  "position_x"),
    "midi_modulation": ("left",  "yaw"),
    "midi_expression": ("right", "openness"),
    "midi_sustain":    None,
    "pitch_bend":      None,
    "midi_cutoff":     ("left",  "position_y"),
    "midi_resonance":  None,
    "midi_reverb":     None,
}


@dataclass
class ControlRouter:
    """Current runtime mapping between (hand, gesture) and outputs."""
    bindings: Dict[str, Binding] = field(
        default_factory=lambda: dict(DEFAULT_BINDINGS)
    )
    selected_index: int = 0
    # Either "midi" (default) or "mac". Mac mode disables all MIDI sends
    # and runs the mac.controller gesture handler instead.
    mode: str = "midi"

    # ── Mode toggle ──────────────────────────

    def toggle_mode(self) -> str:
        self.mode = "mac" if self.mode == "midi" else "midi"
        return self.mode

    def set_mode(self, mode: str) -> None:
        if mode in ("midi", "mac"):
            self.mode = mode

    # ── Selection ────────────────────────────

    def reset_defaults(self) -> None:
        self.bindings = dict(DEFAULT_BINDINGS)

    def selected_param(self) -> str:
        return PARAM_ORDER[self.selected_index % len(PARAM_ORDER)]

    def move_selection(self, delta: int) -> None:
        self.selected_index = (self.selected_index + delta) % len(PARAM_ORDER)

    def select_param(self, param: str) -> None:
        """Jump the selection to a specific param (click-to-focus)."""
        if param in PARAM_ORDER:
            self.selected_index = PARAM_ORDER.index(param)

    # ── Binding read/write ───────────────────

    def get_binding(self, param: str) -> Binding:
        return self.bindings.get(param)

    def set_binding(self, param: str, binding: Binding) -> None:
        if param not in PARAM_ORDER:
            return
        # Validate the binding
        if binding is not None:
            if (not isinstance(binding, tuple) or len(binding) != 2
                    or binding[0] not in HANDS
                    or binding[1] not in FEATURE_NAMES):
                return
        self.bindings[param] = binding

    def cycle_binding(self, param: str, delta: int = 1) -> Binding:
        current = self.bindings.get(param)
        try:
            idx = BINDING_ORDER.index(current)
        except ValueError:
            idx = 0
        idx = (idx + delta) % len(BINDING_ORDER)
        self.bindings[param] = BINDING_ORDER[idx]
        return self.bindings[param]

    def toggle_off_or_default(self, param: str) -> Binding:
        current = self.bindings.get(param)
        if current is None:
            self.bindings[param] = DEFAULT_BINDINGS.get(param)
        else:
            self.bindings[param] = None
        return self.bindings[param]

    # ── Introspection ────────────────────────

    def snapshot(self) -> Dict[str, Binding]:
        return dict(self.bindings)

    def rows(self):
        """Used by the menu to draw the list."""
        selected = self.selected_param()
        return [
            (param, self.bindings.get(param), param == selected)
            for param in PARAM_ORDER
        ]
