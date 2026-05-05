# ─────────────────────────────────────────────
#  music/scale.py
#
#  Chord definitions and MIDI note math.
#  Supports "chord complexity" — the arpeggiator
#  can voice each chord as a simple triad or as
#  a richer extended chord (7th, 9th, add6).
# ─────────────────────────────────────────────

import config


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
              "F#", "G", "G#", "A", "A#", "B"]


# Chord-complexity levels. Each entry says what EXTRA intervals to add on
# top of the base triad that lives in config.CHORD_SET.
#
# The arpeggiator picks one level at a time (via the mapping layer) and
# the voicing includes those extra tones.
#
# Order matters: "triad" is index 0, then progressively lusher. The
# mapping uses a discrete mapping to pick an index.
COMPLEXITY_LEVELS = [
    {"name": "triad",  "extras": []},            # just the base 3 notes
    {"name": "7th",    "extras": [10]},          # + minor 7 (works for both maj/min on this chord set)
    {"name": "add6",   "extras": [9]},           # + major 6
    {"name": "9th",    "extras": [10, 14]},      # + 7 + 9 (lush, Rhodes-ballad feel)
]

# Default complexity when the parameter isn't mapped
DEFAULT_COMPLEXITY = "triad"


def complexity_by_index(index: int) -> dict:
    return COMPLEXITY_LEVELS[index % len(COMPLEXITY_LEVELS)]


def complexity_index_of(name: str) -> int:
    for i, c in enumerate(COMPLEXITY_LEVELS):
        if c["name"] == name:
            return i
    return 0


def midi_to_name(midi: int) -> str:
    """e.g. 60 -> 'C4', 69 -> 'A4'."""
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


def chord_notes(chord_def: dict, octave: int,
                complexity: str = DEFAULT_COMPLEXITY) -> list:
    """
    Build the actual MIDI notes for a chord at a given octave and complexity.

    chord_def: one of config.CHORD_SET entries (has "root" and "intervals")
    octave:    4 = middle octave (C4 = MIDI 60)
    complexity: "triad" | "7th" | "add6" | "9th"

    Returns a list of MIDI note numbers in ascending order.
    """
    base = 12 * (octave + 1) + chord_def["root"]   # MIDI 0 = C-1
    intervals = list(chord_def["intervals"])

    # Find extras for this complexity
    extras = []
    for level in COMPLEXITY_LEVELS:
        if level["name"] == complexity:
            extras = list(level["extras"])
            break

    all_intervals = intervals + extras
    return sorted({base + i for i in all_intervals})


def chord_by_index(index: int) -> dict:
    """Safe modulo indexing into the chord set."""
    n = len(config.CHORD_SET)
    return config.CHORD_SET[index % n]


def chord_name(chord_def: dict) -> str:
    return chord_def["name"]
