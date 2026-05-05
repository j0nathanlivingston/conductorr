# ─────────────────────────────────────────────
#  music/arpeggiator.py
#
#  The arpeggiator state machine.
#
#  On each clock step, chooses the next note based
#  on the current chord + pattern. Delegates
#  sounding to NoteManager so release is clean.
#
#  Modes:
#    "arp"     — cycling notes at the clock rate
#                (up, down, updown, random)
#    "sustain" — all chord notes held; no arp firing
#
#  The mapping layer decides which mode is active
#  (typically based on openness = open/fist).
# ─────────────────────────────────────────────

import random
import threading
from typing import Optional

import config
from music.scale import chord_notes, DEFAULT_COMPLEXITY
from music.note_manager import NoteManager


class Arpeggiator:
    def __init__(self, note_manager: NoteManager):
        self.nm = note_manager
        self._lock = threading.Lock()

        # Musical state set by the mapping layer
        self._chord_def: dict = config.CHORD_SET[0]
        self._octave: int = 4
        self._pattern: str = "up"
        self._mode: str = "arp"       # "arp" or "sustain"
        self._gate_frac: float = 0.5  # fraction of step interval note rings
        self._velocity: int = 90
        self._complexity: str = DEFAULT_COMPLEXITY

        # Iteration state
        self._step_index: int = 0
        self._updown_direction: int = +1

    # ── Setters called by mapping layer (main thread) ──

    def set_chord(self, chord_def: dict):
        with self._lock:
            if chord_def is not self._chord_def:
                # Chord changed — if we're in sustain mode, update the held
                # notes to the new chord so it re-voices cleanly.
                self._chord_def = chord_def
                changed = True
            else:
                changed = False
        if changed and self._mode == "sustain":
            self._apply_sustain()

    def set_octave(self, octave: int):
        with self._lock:
            oct_clamped = max(config.OCTAVE_MIN, min(config.OCTAVE_MAX, int(octave)))
            changed = (oct_clamped != self._octave)
            self._octave = oct_clamped
        if changed and self._mode == "sustain":
            self._apply_sustain()

    def set_complexity(self, complexity: str):
        """triad / 7th / add6 / 9th."""
        with self._lock:
            # Accept any recognised level; ignore garbage silently.
            from music.scale import COMPLEXITY_LEVELS
            valid = {c["name"] for c in COMPLEXITY_LEVELS}
            if complexity in valid and complexity != self._complexity:
                self._complexity = complexity
                changed = True
            else:
                changed = False
        if changed and self._mode == "sustain":
            self._apply_sustain()

    def set_pattern(self, pattern: str):
        with self._lock:
            if pattern in config.ARP_PATTERNS:
                self._pattern = pattern

    def set_gate(self, gate_frac: float):
        with self._lock:
            self._gate_frac = max(config.GATE_MIN,
                                  min(config.GATE_MAX, float(gate_frac)))

    def set_velocity(self, velocity: int):
        with self._lock:
            self._velocity = max(config.VELOCITY_MIN,
                                 min(config.VELOCITY_MAX, int(velocity)))

    def set_mode(self, mode: str):
        """Switch between 'arp' and 'sustain'. Handles note cleanup."""
        if mode not in ("arp", "sustain"):
            return
        with self._lock:
            changed = (mode != self._mode)
            self._mode = mode
        if not changed:
            return
        if mode == "sustain":
            # Drop any arp-timed notes and hold the chord
            self.nm.panic()
            self._apply_sustain()
        else:
            # Drop the held chord, go back to arp firing
            self.nm.release_holds()
            with self._lock:
                self._step_index = 0
                self._updown_direction = +1

    # ── Called on every clock step (clock thread) ──

    def step(self, step_number: int):
        """Called by the clock each subdivision."""
        with self._lock:
            mode = self._mode
            chord_def = self._chord_def
            octave = self._octave
            pattern = self._pattern
            gate = self._gate_frac
            velocity = self._velocity
            complexity = self._complexity

        # Always advance the note manager's timers
        self.nm.tick(step_number)

        if mode == "sustain":
            # Nothing to fire; sustained chord is already held
            return

        # Arp mode — pick next note
        notes = chord_notes(chord_def, octave, complexity)
        if not notes:
            return

        midi = self._pick_next_arp_note(notes, pattern)

        # Gate length in steps — at least 1, at most one step minus a hair
        # (we want the note to release slightly before the next one
        # triggers so retriggers don't overlap).
        # Gate is expressed as a fraction of one step. Since our note_manager
        # works in integer steps, round to at least 1. For very short gates,
        # 1 step is fine.
        gate_steps = max(1, int(round(gate)))

        self.nm.play_note(midi, velocity, gate_steps)

    # ── Internal ─────────────────────────────

    def _pick_next_arp_note(self, notes: list, pattern: str) -> int:
        """Returns the MIDI note to play for this step."""
        n = len(notes)
        with self._lock:
            i = self._step_index
            direction = self._updown_direction

        if pattern == "up":
            note = notes[i % n]
            i_next = i + 1
            direction_next = direction
        elif pattern == "down":
            note = notes[(n - 1 - i) % n]
            i_next = i + 1
            direction_next = direction
        elif pattern == "updown":
            # Go 0, 1, ..., n-1, n-2, ..., 1, 0, 1, ...  (bounce)
            if n <= 1:
                note = notes[0]
                i_next = 0
                direction_next = direction
            else:
                note = notes[i]
                new_i = i + direction
                new_dir = direction
                if new_i >= n:
                    new_i = n - 2
                    new_dir = -1
                elif new_i < 0:
                    new_i = 1
                    new_dir = +1
                i_next = new_i
                direction_next = new_dir
        elif pattern == "random":
            note = random.choice(notes)
            i_next = i + 1
            direction_next = direction
        else:
            note = notes[i % n]
            i_next = i + 1
            direction_next = direction

        with self._lock:
            self._step_index = i_next
            self._updown_direction = direction_next

        return note

    def _apply_sustain(self):
        """Update held notes to match current chord + octave + complexity."""
        with self._lock:
            chord_def = self._chord_def
            octave = self._octave
            velocity = self._velocity
            complexity = self._complexity
        notes = chord_notes(chord_def, octave, complexity)
        self.nm.hold_notes(notes, velocity=velocity)

    # ── Introspection ────────────────────────

    def snapshot(self) -> dict:
        """Return current state for the UI."""
        with self._lock:
            return {
                "chord":      self._chord_def["name"],
                "octave":     self._octave,
                "pattern":    self._pattern,
                "mode":       self._mode,
                "gate":       self._gate_frac,
                "velocity":   self._velocity,
                "complexity": self._complexity,
            }
