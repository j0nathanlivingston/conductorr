# ─────────────────────────────────────────────
#  midi/output.py
#
#  Opens the macOS IAC virtual MIDI port and provides
#  MIDI-protocol helpers for the whole performance
#  subgroup: notes, pitch bend, and the six standard
#  CCs (volume, pan, modulation, expression, sustain).
#
#  Design notes:
#
#  1. Change-detection.
#     main.py may call midi.volume(100) every frame.
#     At 30+ FPS that's 30+ identical CC messages/sec,
#     which is wasteful and can confuse some plugins.
#     We cache the last value sent per CC/pitch-bend
#     and only send when it actually changes.
#
#  2. Thread safety.
#     Clock thread sends note_on/off while the main
#     thread sends CCs and pitch bend. All send paths
#     go through self._lock.
#
#  3. Pitch bend range.
#     MIDI pitch bend is a 14-bit value in [-8192, 8191].
#     mido's "pitchwheel" message handles the encoding;
#     we just pass the signed integer.
# ─────────────────────────────────────────────

import sys
import threading
from typing import Optional

import config

try:
    import mido
except ImportError:
    print(
        "\n[ERROR] The `mido` package is required.\n"
        "Install with:   pip install mido python-rtmidi\n",
        file=sys.stderr,
    )
    raise


# Standard MIDI CC numbers for the performance subgroup
CC_MODULATION = 1
CC_VOLUME     = 7
CC_PAN        = 10
CC_EXPRESSION = 11
CC_SUSTAIN    = 64
CC_RESONANCE  = 71   # filter resonance / timbre
CC_CUTOFF     = 74   # filter cutoff / brightness
CC_REVERB     = 91   # reverb send level


class MidiOut:
    def __init__(self, port_hint: str = config.MIDI_PORT_HINT,
                 channel: int = config.MIDI_CHANNEL):
        self._channel = max(0, min(15, channel))
        self._lock = threading.Lock()
        self._port: Optional[mido.ports.BaseOutput] = None
        self._port_name: str = ""
        self._open(port_hint)

        # Change-detection cache.
        # Keys: CC numbers (int) and the literal string "pitch_bend".
        # Values: last value actually sent on the wire.
        self._last_sent: dict = {}

    def _open(self, port_hint: str):
        names = mido.get_output_names()
        chosen = None
        for n in names:
            if port_hint.lower() in n.lower():
                chosen = n
                break

        if chosen is None:
            listing = "\n".join(f"    {n}" for n in names) or "    (none)"
            print(
                f"\n[ERROR] Couldn't find a MIDI output matching "
                f"'{port_hint}'.\n"
                f"Available ports:\n{listing}\n"
                "On macOS: Audio MIDI Setup → Window → Show MIDI Studio →\n"
                "double-click IAC Driver → check 'Device is online'.\n",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"[MIDI] Opening port: {chosen}")
        self._port = mido.open_output(chosen)
        self._port_name = chosen

    @property
    def port_name(self) -> str:
        return self._port_name

    # ── Low-level send (all messages go through here) ──

    def _send(self, msg):
        with self._lock:
            if self._port is not None:
                self._port.send(msg)

    # ── Notes ────────────────────────────────

    def note_on(self, midi: int, velocity: int = 100):
        msg = mido.Message("note_on",
                           note=int(midi) & 0x7F,
                           velocity=max(1, min(127, int(velocity))),
                           channel=self._channel)
        self._send(msg)

    def note_off(self, midi: int):
        msg = mido.Message("note_off",
                           note=int(midi) & 0x7F,
                           velocity=0,
                           channel=self._channel)
        self._send(msg)

    # ── Raw CC ───────────────────────────────

    def cc(self, controller: int, value: int):
        """Send a raw MIDI CC (always, no change-detection).
        Use the named helpers below if you want change-detection."""
        msg = mido.Message("control_change",
                           control=int(controller) & 0x7F,
                           value=max(0, min(127, int(value))),
                           channel=self._channel)
        self._send(msg)

    def _cc_if_changed(self, cc_num: int, value: int):
        """Send a CC only if its value differs from the last one we sent."""
        v = max(0, min(127, int(value)))
        if self._last_sent.get(cc_num) == v:
            return
        self._last_sent[cc_num] = v
        self.cc(cc_num, v)

    # ── MIDI subgroup — named helpers ────────

    def volume(self, value: int):
        """CC 7 — channel volume (0..127)."""
        self._cc_if_changed(CC_VOLUME, value)

    def pan(self, value: int):
        """CC 10 — pan (0 = hard left, 64 = centre, 127 = hard right)."""
        self._cc_if_changed(CC_PAN, value)

    def modulation(self, value: int):
        """CC 1 — mod wheel (0..127)."""
        self._cc_if_changed(CC_MODULATION, value)

    def expression(self, value: int):
        """CC 11 — expression (0..127). Acts as a secondary volume;
        most synths multiply volume and expression."""
        self._cc_if_changed(CC_EXPRESSION, value)

    def sustain(self, on: bool):
        """CC 64 — damper pedal. Convention: 0..63 = off, 64..127 = on.
        We send 0 or 127."""
        target = 127 if on else 0
        self._cc_if_changed(CC_SUSTAIN, target)

    def cutoff(self, value: int):
        """CC 74 — filter cutoff / brightness. The #1 most expressive
        CC on most synth-style GarageBand patches."""
        self._cc_if_changed(CC_CUTOFF, value)

    def resonance(self, value: int):
        """CC 71 — filter resonance / timbre. Squelchy when paired with
        cutoff sweeps."""
        self._cc_if_changed(CC_RESONANCE, value)

    def reverb_send(self, value: int):
        """CC 91 — reverb send level. Works on most GarageBand built-in
        instruments to control the wet/dry feel."""
        self._cc_if_changed(CC_REVERB, value)

    def pitch_bend(self, value: int):
        """14-bit signed pitch bend in [-8192, 8191].
        0 = no bend. mido's 'pitchwheel' message handles the encoding."""
        v = max(-8192, min(8191, int(value)))
        if self._last_sent.get("pitch_bend") == v:
            return
        self._last_sent["pitch_bend"] = v
        msg = mido.Message("pitchwheel",
                           pitch=v,
                           channel=self._channel)
        self._send(msg)

    # ── Panic / cleanup ──────────────────────

    def all_notes_off(self):
        """CC 123 — all notes off on our channel."""
        self.cc(123, 0)

    def reset_performance_controls(self):
        """Reset pitch bend + sustain to neutral values. Called on close."""
        try:
            self.pitch_bend(0)
        except Exception:
            pass
        try:
            self.sustain(False)
        except Exception:
            pass

    def close(self):
        with self._lock:
            if self._port is not None:
                try:
                    # Neutralise performance controls before closing,
                    # so the instrument doesn't get stuck in a bent /
                    # sustained state.
                    msg = mido.Message("pitchwheel", pitch=0,
                                       channel=self._channel)
                    self._port.send(msg)
                    msg = mido.Message("control_change",
                                       control=CC_SUSTAIN, value=0,
                                       channel=self._channel)
                    self._port.send(msg)
                    msg = mido.Message("control_change",
                                       control=123, value=0,
                                       channel=self._channel)
                    self._port.send(msg)
                except Exception:
                    pass
                self._port.close()
                self._port = None
