# ─────────────────────────────────────────────
#  music/clock.py
#
#  BPM clock running in a background thread.
#  Fires `on_step` callbacks at every subdivision
#  (16th notes by default).
#
#  Supports live BPM updates — the main thread
#  can call set_bpm() whenever the mapping layer
#  decides the tempo has changed.
#
#  Uses drift-corrected absolute-time scheduling
#  so small sleep jitter doesn't accumulate.
# ─────────────────────────────────────────────

import threading
import time
from typing import Callable, Optional
import config


class Clock:
    def __init__(self, bpm: float = config.DEFAULT_BPM,
                 subdivision: int = config.SUBDIVISION):
        self._bpm = float(bpm)
        self._subdiv = subdivision
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._step_callbacks: list = []
        self.step_number = 0

    # ── Callbacks ────────────────────────────

    def on_step(self, fn: Callable[[int], None]):
        """Call fn(step_number) at every subdivision."""
        self._step_callbacks.append(fn)

    # ── Control ──────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="ClockThread")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def set_bpm(self, bpm: float):
        with self._lock:
            self._bpm = max(config.BPM_MIN, min(config.BPM_MAX, float(bpm)))

    @property
    def bpm(self) -> float:
        with self._lock:
            return self._bpm

    @property
    def step_interval(self) -> float:
        with self._lock:
            return 60.0 / self._bpm / self._subdiv

    # ── Internal ─────────────────────────────

    def _run(self):
        next_time = time.perf_counter()
        while self._running:
            # Fire callbacks
            for fn in self._step_callbacks:
                try:
                    fn(self.step_number)
                except Exception as e:
                    print(f"[Clock] step callback error: {e}")
            self.step_number += 1

            # Drift-corrected sleep
            next_time += self.step_interval
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_time = time.perf_counter()   # resync after lag spike
