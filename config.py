# ─────────────────────────────────────────────
#  config.py  –  Global constants.
#  Everything tuneable lives here.
# ─────────────────────────────────────────────

# ── Camera ──────────────────────────────────
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
MIRROR_CAMERA = True             # flip horizontally so it feels like a mirror

# ── MediaPipe hand tracking ─────────────────
MP_MODEL_COMPLEXITY = 0           # 0 = fastest, 1 = more accurate
MP_MIN_DETECTION_CONFIDENCE = 0.6
MP_MIN_TRACKING_CONFIDENCE = 0.5

# ── MIDI ────────────────────────────────────
MIDI_PORT_HINT = "IAC"            # substring matched against available ports
MIDI_CHANNEL = 0                  # 0-indexed (MIDI channel 1)

# If True, we also send CC (filter cutoff) based on a mapped feature.
# Off by default for max compatibility across GarageBand instruments.
ENABLE_CC = False
CC_NUMBER = 74                    # 74 is filter cutoff on most synths

# ── Music defaults ──────────────────────────
DEFAULT_BPM = 110

# The 4 chords the user cycles through via position_x by default.
# Each chord is a list of scale-degree / MIDI offset pairs.  We store them
# as (root MIDI note, [interval list]) and build the actual notes at
# render time based on the current octave.
#
# Classic "sad loop": Am - F - C - G
CHORD_SET = [
    {"name": "Am", "root": 9,  "intervals": [0, 3, 7]},    # A C  E
    {"name": "F",  "root": 5,  "intervals": [0, 4, 7]},    # F A  C
    {"name": "C",  "root": 0,  "intervals": [0, 4, 7]},    # C E  G
    {"name": "G",  "root": 7,  "intervals": [0, 4, 7]},    # G B  D
]

# Available arpeggio patterns. Names used by the mapping layer.
ARP_PATTERNS = ["up", "down", "updown", "random"]

# Allowed tempo range when tempo is mapped to a feature
BPM_MIN = 70
BPM_MAX = 160

# Allowed octave range when octave is mapped to a feature
OCTAVE_MIN = 3
OCTAVE_MAX = 6

# MIDI velocity range when velocity is mapped
VELOCITY_MIN = 55
VELOCITY_MAX = 120

# Gate length (fraction of a 16th-note interval that the note rings for)
GATE_MIN = 0.15
GATE_MAX = 0.90

# ── Feature smoothing ───────────────────────
# Exponential moving average alpha. Higher = more responsive, more jittery.
EMA_ALPHA = 0.35

# Feature thresholds — tuned empirically
OPENNESS_FIST = 0.35               # normalised openness below this = "fist"
OPENNESS_OPEN = 0.55               # above this = "open" (hysteresis gap between)

# ── Clock ───────────────────────────────────
SUBDIVISION = 4                   # 4 = 16th notes per beat

# ── UI ──────────────────────────────────────
WINDOW_NAME = "Hand Arpeggiator"
SHOW_LANDMARKS = True
