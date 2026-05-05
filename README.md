# 🖐️🖐️ Conductor

A webcam-based gestural arpeggiator in Python. Tracks **up to two hands**
with MediaPipe, extracts 7 continuous features per hand, and maps any
feature on either hand to any musical parameter through a live,
clickable control menu. The arpeggiator sends MIDI to GarageBand (or any
other MIDI-capable DAW) via the macOS IAC driver.

Built for the *Principles of Programming* course project.

---

## What it does

- **Tracks up to two hands** in real time (MediaPipe Hands)
- **Extracts 7 features per hand**: `position_x`, `position_y`,
  `pitch`, `yaw`, `roll`, `velocity`, `openness`
- **Any feature on either hand can control any musical parameter** —
  rebind live by clicking the control menu, no restart needed
- **Drives an arpeggiator engine** in Python — 4 patterns (up, down,
  updown, random) and 2 modes (arpeggiated / sustained chord)
- **Chord complexity** — triad / 7th / add6 / 9th, voiced by the arpeggiator
- **Full MIDI performance subgroup**: note velocity, volume, pan,
  modulation, expression, sustain, pitch bend, and the three expressive
  CCs (filter cutoff, resonance, reverb send)
- **Sends MIDI** to GarageBand via macOS IAC
- **Shows a live HUD** on the camera feed: all 7 feature values, all 6
  musical parameters, and a 4-beat pulse indicator

---

## Setup

### One-time macOS setup

1. Open **Audio MIDI Setup** (Spotlight → type the name → Enter)
2. Menu: **Window → Show MIDI Studio**
3. Double-click **IAC Driver**
4. Check **"Device is online"** and click **Apply**
5. Close Audio MIDI Setup

### GarageBand

1. Open GarageBand → **Empty Project**
2. Track type: **Software Instrument**
3. Pick any instrument — a synth lead, strings, or piano all work well
4. Leave the track armed (small monitor/headphones icon lit)

GarageBand now listens for MIDI on all ports by default. The IAC driver
is one of them.

### Python environment

Requires Python **3.11** or **3.12** (MediaPipe wheels don't yet exist
for 3.13+).

```bash
# With uv (recommended)
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt

# Or plain pip
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Run

```bash
python main.py
```

The window opens, the camera starts, and you should see:
- Your camera feed (mirrored, so it feels like a mirror)
- Hand skeleton drawn on the hand when it's detected
- A **FEATURES** panel (top-left) showing live values for all 7 features
- A **MUSIC** panel (top-right) showing the current chord, octave,
  tempo, pattern, gate length, velocity, and mode
- A **4-beat pulse** indicator at the bottom centre

Move your hand around. You should hear arpeggiated notes in GarageBand
that respond continuously to your hand's motion.

Press **Q** or **ESC** to quit.

---

## Default control mapping

Right hand drives the core musical controls. Left hand provides
secondary expression (chord complexity, pan, modulation, filter cutoff).
Anything can be rebound live.

| Parameter | Default binding | Effect |
|---|---|---|
| **Chord** | R: position_x | Left/right splits into 4 chord zones: Am → F → C → G |
| **Octave** | R: position_y | Higher hand = higher octave (3–6) |
| **Tempo** | R: roll | Doorknob rotation; 70–160 BPM |
| **Pattern** | R: yaw | Turns through up/down/updown/random |
| **Gate length** | R: pitch | Palm forward = longer notes |
| **Note velocity** | R: velocity | Motion speed → MIDI velocity |
| **Mode** | R: openness | Open = arpeggiate, fist = sustain chord |
| **Chord complexity** | L: openness | Fist = triad → spread = 9th chord |
| **MIDI Pan** | L: position_x | Left hand X pans the stereo image |
| **MIDI Modulation (CC 1)** | L: yaw | Mod wheel |
| **MIDI Expression (CC 11)** | R: openness | Openness swells loudness |
| **Filter Cutoff (CC 74)** | L: position_y | Left hand up/down = brighter/darker |
| **MIDI Volume** | *(off)* | Bind in the menu |
| **MIDI Sustain** | *(off)* | Bind in the menu |
| **Pitch Bend** | *(off)* | Bind in the menu |
| **Resonance (CC 71)** | *(off)* | Bind in the menu |
| **Reverb Send (CC 91)** | *(off)* | Bind in the menu |

---

## Control menu (clickable)

When the app runs, a second window called **Control Menu** opens. It
lists every musical parameter, which hand+gesture currently controls it,
and an OFF button for each.

**Click to remap:**
1. Click the binding cell (the blue box showing the current gesture) —
   a dropdown appears listing every option (OFF, L: Hand X, L: Yaw, ...)
2. Click one — binding is set, dropdown closes.
3. Click the red **X** button on a row to disable that parameter.
4. Click outside an open dropdown to close it without changing anything.

**Keyboard shortcuts (also work):**

| Key | Action |
|---|---|
| `J` / `K` | Move selection down / up |
| `L` / `H` | Cycle selected binding forward / backward through all 15 options |
| `X` | Toggle OFF, or restore default |
| `R` | Reset all to defaults |
| `Q` / `ESC` | Quit |

Keys work from either window, whichever has OpenCV focus.

**Example — bind pitch bend to left-hand yaw:**
1. Click the binding cell on the "Pitch Bend" row
2. Click "L: Yaw / Turn" in the dropdown
3. Turn your left hand — you'll hear the pitch bending smoothly

---

## Remapping by editing code (permanent)

The control menu changes are runtime-only; they reset when you quit.
For **permanent** default changes, edit `mapping/control_router.py` —
the `DEFAULT_BINDINGS` dict at the top is what the router loads on
startup and what `R` resets to.

Example — make pitch bend respond to yaw by default:

```python
DEFAULT_BINDINGS = {
    ...
    "pitch_bend": "yaw",    # was: None
}
```

---

## Project structure

```
hand-arpeggiator/
├── main.py                    # Main loop: wires everything together
├── config.py                  # BPM, MIDI port, chord set, thresholds
├── requirements.txt
├── README.md
│
├── vision/
│   ├── camera.py              # Webcam opener
│   └── tracker.py             # MediaPipe hand tracker
│
├── features/
│   ├── hand_features.py       # landmarks → 7 features
│   └── smoothing.py           # EMA smoothing
│
├── music/
│   ├── scale.py               # Chord and MIDI note math
│   ├── clock.py               # BPM clock (background thread)
│   ├── note_manager.py        # Guarantees note_on/note_off pairing
│   └── arpeggiator.py         # The arpeggiator state machine
│
├── mapping/
│   ├── mapping.py             # Applies the runtime bindings each frame
│   └── control_router.py      # The live binding table (router)
│
├── midi/
│   └── output.py              # IAC port, notes, CCs, pitch bend (change-detected)
│
└── ui/
    ├── overlay.py             # Live HUD on the camera feed
    └── control_menu.py        # Second window: the live binding editor
```

---

## Design notes

### Separation of concerns

Each module can be replaced without touching the others:
- Change the tracker → swap `vision/tracker.py`
- Change the arp patterns → edit `music/arpeggiator.py`
- Change the hand-to-music mapping → edit `mapping/mapping.py`
- Send to a different DAW / plugin → edit `midi/output.py`

This is what lets you remap any feature to any parameter with a
single-line change.

### Why pitch/yaw/roll are approximated from landmark vectors

Full 6-DOF hand pose from a single webcam requires solving PnP with a
3D hand model. That's its own computer-vision project. Instead we
compute three intuitive axes from vectors between known landmarks:

- **UP vector**: wrist → middle-finger knuckle
- **ACROSS vector**: index-finger knuckle → pinky knuckle
- **PALM NORMAL**: cross product of UP and ACROSS

From these:
- **Yaw** is the XY-plane angle of UP (hand pointing left vs right)
- **Roll** is the XY-plane angle of ACROSS (doorknob rotation)
- **Pitch** is the Z-component of PALM NORMAL (palm facing camera vs
  facing away)

These are noisy in absolute terms but monotonic and responsive, which
is what an expressive musical control needs.

### Why the note manager exists

Without explicit tracking, MIDI "stuck notes" are inevitable. The
arpeggiator changes pattern or the user closes their fist mid-phrase,
and a `note_on` that never got a matched `note_off` keeps ringing in
GarageBand forever. `NoteManager` tracks every active note and
guarantees cleanup on mode changes, chord changes, and app exit
(plus a MIDI "All Notes Off" as a final safety net on shutdown).

### Why an EMA smoother sits between the extractor and the mapping

Raw MediaPipe landmarks jitter frame-to-frame even when the hand is
still. Feeding jittery features into a quantised musical parameter
would cause rapid flickering between chords or patterns. The
exponential moving average is cheap and feels natural — higher alpha =
snappier response, lower alpha = heavier smoothing. Tuned empirically
to `0.35` in `config.py`.

### Why the clock runs on its own thread

A camera frame loop runs at ~30 FPS (~33 ms per frame), but 16th notes
at 160 BPM are 93 ms apart. We'd still catch each beat, but timing
jitter would be on the order of the frame interval. A dedicated clock
thread with drift-corrected `time.sleep` keeps note timing tight
(usually within 1–2 ms) regardless of what the camera thread is doing.

---

## Troubleshooting

**"Couldn't find a MIDI output matching 'IAC'."**
You skipped the IAC setup. Go back to the one-time macOS setup above.

**Script runs but no sound in GarageBand.**
GarageBand track isn't armed, or isn't a Software Instrument. Create a
new Software Instrument track, pick an instrument, and look for the
monitor icon on the track header.

**MediaPipe install fails.**
Pin Python 3.11 or 3.12 (not 3.13+). If you see `AttributeError: module
'mediapipe' has no attribute 'solutions'`, the wrong build got
installed — reinstall with `pip install mediapipe==0.10.14`.

**Notes hang after quitting mid-phrase.**
In GarageBand, press `Fn + F` or click anywhere in the track list to
send All Notes Off manually. The app sends one on clean exit, but a
hard kill (Ctrl-C, window close) may skip it on some systems.

**Hand tracking is laggy.**
Lower the camera resolution in `config.py` — `FRAME_WIDTH = 640,
FRAME_HEIGHT = 480` doubles the frame rate on modest hardware.

---

## Possible extensions

- MIDI CC (filter cutoff / mod wheel) for continuous timbral control —
  flip `ENABLE_CC = True` in `config.py` and add a CC rule to `MAPPING`
- Two-hand support (second hand controls effects, first controls notes)
- Per-preset mapping files (load `mapping_dark.json`, `mapping_bright.json`)
- Record the MIDI stream to a `.mid` file for later playback
- Voice guidance that announces chord changes (for solo practice)
