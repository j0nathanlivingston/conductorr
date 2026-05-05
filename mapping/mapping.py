# ─────────────────────────────────────────────
# mapping/mapping.py
#
# Runtime mapping layer.
#
# Input:
#   per_hand_features = {
#       "left":  {position_x, position_y, pitch, yaw, roll, velocity, openness}
#                or None,
#       "right": {...} or None,
#   }
#   plus a ControlRouter that knows which (hand, feature) controls what.
#
# Output:
#   - pushes musical-parameter values into the arpeggiator and clock
#   - returns a dict of resolved values for main.py to send as MIDI
# ─────────────────────────────────────────────

from typing import Optional, Tuple

import config
from music.scale import (
    chord_by_index, COMPLEXITY_LEVELS, DEFAULT_COMPLEXITY,
    complexity_by_index,
)
from mapping.control_router import ControlRouter, DEFAULT_BINDINGS


FEATURE_RANGES = {
    "position_x": (0.0, 1.0),
    "position_y": (0.0, 1.0),
    "pitch":      (-1.0, 1.0),
    "yaw":        (-1.0, 1.0),
    "roll":       (-1.0, 1.0),
    "velocity":   (0.0, 1.0),
    "openness":   (0.0, 1.0),
}


DEFAULTS = {
    "chord":           0,
    "octave":          4,
    "tempo":           config.DEFAULT_BPM,
    "pattern":         "up",
    "gate":            0.5,
    "velocity":        90,
    "mode":            "sustain",
    "complexity":      DEFAULT_COMPLEXITY,
    "midi_volume":     100,
    "midi_pan":        64,
    "midi_modulation": 0,
    "midi_expression": 127,
    "midi_sustain":    0,
    "pitch_bend":      0,
    "midi_cutoff":     64,
    "midi_resonance":  0,
    "midi_reverb":     40,
}


# ── Helpers ────────────────────────────────

def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _normalise(feature_name: str, value: float) -> float:
    lo, hi = FEATURE_RANGES[feature_name]
    if hi == lo:
        return 0.5
    return _clamp01((value - lo) / (hi - lo))


def _feature_value(per_hand_features: dict, binding) -> Optional[float]:
    """
    Look up the feature value for a given binding.
    binding = (hand, feature_name) or None.
    Returns None if the binding is None, the hand isn't detected, or the
    feature isn't in the dict.
    """
    if binding is None:
        return None
    hand, feat = binding
    hand_features = per_hand_features.get(hand) if per_hand_features else None
    if not hand_features:
        return None
    return hand_features.get(feat)


def _normalised(per_hand_features: dict, binding) -> Optional[float]:
    """Get a binding's raw value and normalise it to 0..1. None if missing."""
    raw = _feature_value(per_hand_features, binding)
    if raw is None:
        return None
    return _normalise(binding[1], raw)


# ── Main entrypoint ────────────────────────

def apply(per_hand_features: Optional[dict],
          arp, clock,
          router: Optional[ControlRouter] = None):
    """
    Apply the router bindings and return a UI-friendly dict.

    per_hand_features: {"left": {...} | None, "right": {...} | None}
                       or None entirely if no hands are detected.
    """
    resolved = {}

    # Start from current live state so disabled params keep their existing value.
    snap = arp.snapshot()
    resolved["chord_name"] = snap.get("chord")
    resolved["octave"]     = snap.get("octave")
    resolved["pattern"]    = snap.get("pattern")
    resolved["mode"]       = snap.get("mode")
    resolved["gate"]       = snap.get("gate")
    resolved["velocity"]   = snap.get("velocity")
    resolved["complexity"] = snap.get("complexity", DEFAULT_COMPLEXITY)
    resolved["tempo"]      = clock.bpm

    bindings = router.snapshot() if router is not None else dict(DEFAULT_BINDINGS)
    resolved["bindings"] = bindings

    # Always expose MIDI defaults so main.py has safe values to send.
    for k in ("midi_volume", "midi_pan", "midi_modulation", "midi_expression",
              "midi_sustain", "pitch_bend",
              "midi_cutoff", "midi_resonance", "midi_reverb"):
        resolved[k] = DEFAULTS[k]

    # Normalise: unify "no hand at all" to an empty dict of hands
    if per_hand_features is None:
        per_hand_features = {}

    # ── Arpeggiator / note-engine params ──

    # chord: discrete, picks a chord index from CHORD_SET
    b = bindings.get("chord")
    n = _normalised(per_hand_features, b)
    if n is not None:
        count = len(config.CHORD_SET)
        chord_idx = min(count - 1, int(n * count))
        chord_def = chord_by_index(chord_idx)
        arp.set_chord(chord_def)
        resolved["chord_name"] = chord_def["name"]

    # octave: range, inverted (higher hand = higher octave)
    b = bindings.get("octave")
    n = _normalised(per_hand_features, b)
    if n is not None:
        # Invert position_y so up = higher octave
        if b[1] == "position_y":
            n = 1.0 - n
        octave = int(round(config.OCTAVE_MIN + n * (config.OCTAVE_MAX - config.OCTAVE_MIN)))
        arp.set_octave(octave)
        resolved["octave"] = octave

    # tempo
    b = bindings.get("tempo")
    n = _normalised(per_hand_features, b)
    if n is not None:
        tempo = config.BPM_MIN + n * (config.BPM_MAX - config.BPM_MIN)
        clock.set_bpm(tempo)
        resolved["tempo"] = tempo

    # pattern: discrete
    b = bindings.get("pattern")
    n = _normalised(per_hand_features, b)
    if n is not None:
        count = len(config.ARP_PATTERNS)
        idx = min(count - 1, int(n * count))
        pattern = config.ARP_PATTERNS[idx]
        arp.set_pattern(pattern)
        resolved["pattern"] = pattern

    # gate
    b = bindings.get("gate")
    n = _normalised(per_hand_features, b)
    if n is not None:
        gate = config.GATE_MIN + n * (config.GATE_MAX - config.GATE_MIN)
        arp.set_gate(gate)
        resolved["gate"] = gate

    # velocity
    b = bindings.get("velocity")
    n = _normalised(per_hand_features, b)
    if n is not None:
        vel = int(round(
            config.VELOCITY_MIN + n * (config.VELOCITY_MAX - config.VELOCITY_MIN)
        ))
        arp.set_velocity(vel)
        resolved["velocity"] = vel

    # mode: threshold on the normalised value
    b = bindings.get("mode")
    n = _normalised(per_hand_features, b)
    if n is not None:
        mode = "arp" if n > 0.60 else "sustain"
        arp.set_mode(mode)
        resolved["mode"] = mode

    # complexity: discrete pick from COMPLEXITY_LEVELS
    b = bindings.get("complexity")
    n = _normalised(per_hand_features, b)
    if n is not None:
        count = len(COMPLEXITY_LEVELS)
        idx = min(count - 1, int(n * count))
        complexity_name = COMPLEXITY_LEVELS[idx]["name"]
        arp.set_complexity(complexity_name)
        resolved["complexity"] = complexity_name

    # ── MIDI subgroup ──

    # Simple 0..127 CCs that map directly from the feature's 0..1 normalised
    for param in ("midi_volume", "midi_pan", "midi_modulation", "midi_expression",
                  "midi_cutoff", "midi_resonance", "midi_reverb"):
        b = bindings.get(param)
        n = _normalised(per_hand_features, b)
        if n is not None:
            resolved[param] = int(round(127 * n))

    # Sustain: 0 or 127, above/below 0.6
    b = bindings.get("midi_sustain")
    n = _normalised(per_hand_features, b)
    if n is not None:
        resolved["midi_sustain"] = 127 if n > 0.60 else 0

    # Pitch bend: 14-bit signed, centred at 0. Full bend = ±8191.
    b = bindings.get("pitch_bend")
    n = _normalised(per_hand_features, b)
    if n is not None:
        bend = int(round((2.0 * n - 1.0) * 8191.0))
        resolved["pitch_bend"] = max(-8192, min(8191, bend))

    return resolved
