# ─────────────────────────────────────────────
#  music/note_manager.py
#
#  Tracks which MIDI notes are currently sounding
#  and guarantees every note_on eventually gets a
#  matched note_off.
#
#  Why this exists:
#    Without tracking, "hang notes" are inevitable.
#    A note gets sent, then the arpeggiator changes
#    mode / chord / pattern, and the note_off gets
#    forgotten. Result: stuck drone in GarageBand,
#    ruins the demo.
#
#  Responsibilities:
#    - play_note(midi, duration_steps)
#        register a timed short note; it will be
#        released automatically after that many
#        clock steps
#    - hold_notes(midi_list)
#        set the current "held" set; notes in the
#        new set that weren't held before are turned
#        on; notes that were held but aren't in the
#        new set are turned off. Used for sustained
#        chord mode.
#    - panic()
#        turn every currently sounding note off.
#        Called on mode switches, reset, and app exit.
#
#  Thread-model:
#    tick() is called from the clock thread.
#    play_note / hold_notes / panic are called from
#    the main thread (or the mapping step).
#    All mutation goes through _lock.
# ─────────────────────────────────────────────

import threading
from typing import Callable, Optional


class NoteManager:
    def __init__(self,
                 note_on_fn: Callable[[int, int], None],
                 note_off_fn: Callable[[int], None]):
        """
        note_on_fn(midi, velocity) and note_off_fn(midi) are the MIDI
        output callbacks. This class is agnostic to what they do (send
        MIDI, print to console, etc.) — they're supplied at construction.
        """
        self._note_on  = note_on_fn
        self._note_off = note_off_fn
        self._lock = threading.Lock()

        # Timed notes: midi -> remaining steps until release.
        # If a note is re-triggered while still ringing, we just reset its timer.
        self._timed: dict = {}

        # Sustained notes: midi -> present (True). These never time out;
        # they stay on until hold_notes() with a different set releases them,
        # or panic() fires.
        self._held: set = set()

    # ── Actions (main thread) ────────────────

    def play_note(self, midi: int, velocity: int, duration_steps: int):
        """
        Trigger a short note that will auto-release after duration_steps
        ticks of the clock. duration_steps must be >= 1.
        """
        if duration_steps < 1:
            duration_steps = 1
        with self._lock:
            if midi in self._held:
                # Currently held as part of a sustained chord — don't
                # interfere with it.
                return
            if midi in self._timed:
                # Still ringing — just reset the timer, don't retrigger.
                # Retriggering would cause a perceived click.
                self._timed[midi] = duration_steps
                return
            self._timed[midi] = duration_steps
        # Fire note_on outside the lock — the callback may take time
        self._note_on(midi, velocity)

    def hold_notes(self, midi_list: list, velocity: int = 90):
        """
        Make exactly this set of notes be held. Any currently-held notes
        not in the new set are released; any new notes are started.
        """
        new_set = set(midi_list)

        with self._lock:
            to_release = self._held - new_set
            to_start   = new_set - self._held
            self._held = set(new_set)

        for midi in to_release:
            self._note_off(midi)
        for midi in to_start:
            # If this note is also timed-ringing, we just promote it — but
            # we need to retrigger at the held velocity for consistency.
            # Simpler: if it's in timed, leave timed entry; then send note_on.
            self._note_on(midi, velocity)

    def release_holds(self):
        """Stop the sustained chord without touching timed notes."""
        with self._lock:
            to_release = set(self._held)
            self._held.clear()
        for midi in to_release:
            self._note_off(midi)

    def panic(self):
        """Turn off every sounding note. Call on mode changes, reset, exit."""
        with self._lock:
            timed = list(self._timed.keys())
            held  = list(self._held)
            self._timed.clear()
            self._held.clear()
        for midi in timed:
            self._note_off(midi)
        for midi in held:
            self._note_off(midi)

    # ── Clock tick (clock thread) ────────────

    def tick(self, step_number: int):
        """
        Called every clock step. Decrements timed notes and releases
        any whose timer hits zero.
        """
        to_release = []
        with self._lock:
            for midi in list(self._timed.keys()):
                self._timed[midi] -= 1
                if self._timed[midi] <= 0:
                    to_release.append(midi)
                    del self._timed[midi]
        # Fire note_off outside the lock
        for midi in to_release:
            self._note_off(midi)

    # ── Introspection ────────────────────────

    def active_count(self) -> int:
        with self._lock:
            return len(self._timed) + len(self._held)
