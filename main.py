#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  main.py  –  Hand-Arpeggiator
#
#  Two modes, toggled from the control menu:
#
#   MIDI mode (default):
#     camera → tracker → features → smoother → mapping → arp/clock → MIDI
#
#   MAC mode:
#     camera → tracker → features → smoother → MacController
#        → AppleScript (spaces, Mission Control, volume, brightness)
#     MIDI is panicked on entry; no notes are sent while in this mode.
#
#  Two windows:
#    - Camera feed with HUD (both hands' feature panels)
#    - Control Menu (clickable dropdowns, with a big mode-toggle button)
#
#  Controls:
#    Q / ESC     : quit
#    J / K       : menu selection down / up
#    H / L       : cycle selected binding backward / forward
#    X           : toggle OFF / restore default
#    R           : reset all mappings to defaults
# ─────────────────────────────────────────────

import cv2
import time
import config
from vision.camera import open_camera
from vision.tracker import HandTracker
from features.hand_features import MultiHandExtractor
from features.smoothing import MultiHandSmoother

from music.clock import Clock
from music.note_manager import NoteManager
from music.arpeggiator import Arpeggiator

from mapping.mapping import apply as apply_mapping
from mapping.control_router import ControlRouter

from midi.output import MidiOut

from ui.overlay import (
    draw_both_feature_panels,
    draw_music_panel,
    draw_beat_indicator,
    draw_footer,
    put_text,
)
from ui.control_menu import ControlMenu, WINDOW_NAME as MENU_WINDOW_NAME
from mac.controller import MacController, IS_MACOS


def show_startup_logo(path, duration=5):
    img = cv2.imread(path)

    if img is None:
        print(f"Could not load logo at {path}")
        return

    window_name = "Starting..."
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    start_time = time.time()

    while True:
        cv2.imshow(window_name, img)

        # waitKey is required for window to update
        if cv2.waitKey(30) & 0xFF == 27:
            break

        if time.time() - start_time > duration:
            break

    cv2.destroyWindow(window_name)



def main():
    show_startup_logo("ui/logo.png", duration=5)
    print("=" * 60)
    print("  Hand-Arpeggiator")
    print("=" * 60)

    # ── Router + menu + Mac controller ──
    router = ControlRouter()
    mac_ctrl = MacController(active_hand="right")

    # Forward-declare `midi` and `arp` so the on_mode_change callback can
    # reach them via closure.
    midi_ref = [None]
    arp_ref  = [None]
    note_mgr_ref = [None]

    def on_mode_change(new_mode: str):
        """Called when user clicks the MIDI/MAC toggle button in the menu."""
        print(f"[Mode] → {new_mode.upper()}")
        if new_mode == "mac":
            # Stop all sound before switching
            if note_mgr_ref[0] is not None:
                note_mgr_ref[0].panic()
            if midi_ref[0] is not None:
                # Neutralise performance CCs too
                try:
                    midi_ref[0].pitch_bend(0)
                    midi_ref[0].sustain(False)
                    midi_ref[0].all_notes_off()
                except Exception as e:
                    print(f"[Mode] MIDI neutralise failed: {e}")
            mac_ctrl.set_enabled(True)
            if not IS_MACOS:
                print("[Mode] WARNING: not running on macOS — Mac actions will be no-ops.")
        else:
            mac_ctrl.set_enabled(False)

    menu = ControlMenu(router, on_mode_change=on_mode_change)

    # ── MIDI ──
    midi = MidiOut()
    midi_ref[0] = midi

    # ── Music engine ──
    note_manager = NoteManager(
        note_on_fn=midi.note_on,
        note_off_fn=midi.note_off,
    )
    note_mgr_ref[0] = note_manager
    arp = Arpeggiator(note_manager)
    arp_ref[0] = arp
    clock = Clock(bpm=config.DEFAULT_BPM, subdivision=config.SUBDIVISION)
    clock.on_step(arp.step)

    # ── Vision ──
    cap = open_camera()
    tracker = HandTracker()
    extractor = MultiHandExtractor()
    smoother = MultiHandSmoother()

    clock.start()
    print(f"[OK] Clock started at {config.DEFAULT_BPM} BPM.")
    print(f"[OK] Using MIDI port: {midi.port_name}")
    print(f"[OK] macOS detected: {IS_MACOS}")
    print("[Info] Two-hand tracking enabled.")
    print("[Info] Q/ESC to quit. Click the menu to remap; keys J/K/H/L/X/R also work.")
    print("[Info] Click the green button at the top of the menu to switch to Mac mode.\n")

    cv2.namedWindow(config.WINDOW_NAME)
    cv2.namedWindow(MENU_WINDOW_NAME)
    cv2.setMouseCallback(MENU_WINDOW_NAME, lambda ev, x, y, flags, param:
                         menu.handle_mouse(ev, x, y))

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[WARN] Failed to read frame; retrying...")
                continue

            if config.MIRROR_CAMERA:
                frame = cv2.flip(frame, 1)

            hands_dict, annotated = tracker.process(frame)
            raw_per_hand = extractor.extract(hands_dict)
            per_hand = smoother.smooth(raw_per_hand)

            mode = router.mode

            if mode == "midi":
                # ── Normal musical operation ──
                resolved = apply_mapping(per_hand, arp, clock, router=router)
                bindings = resolved.get("bindings", {})

                # Route CCs — disabled bindings get neutral fallbacks
                if bindings.get("midi_volume") is not None:
                    midi.volume(int(resolved["midi_volume"]))
                else:
                    midi.volume(100)

                if bindings.get("midi_pan") is not None:
                    midi.pan(int(resolved["midi_pan"]))
                else:
                    midi.pan(64)

                if bindings.get("midi_modulation") is not None:
                    midi.modulation(int(resolved["midi_modulation"]))
                else:
                    midi.modulation(0)

                if bindings.get("midi_expression") is not None:
                    midi.expression(int(resolved["midi_expression"]))
                else:
                    midi.expression(127)

                if bindings.get("midi_sustain") is not None:
                    midi.sustain(int(resolved["midi_sustain"]) >= 64)
                else:
                    midi.sustain(False)

                if bindings.get("pitch_bend") is not None:
                    midi.pitch_bend(int(resolved["pitch_bend"]))
                else:
                    midi.pitch_bend(0)

                if bindings.get("midi_cutoff") is not None:
                    midi.cutoff(int(resolved["midi_cutoff"]))
                else:
                    midi.cutoff(64)

                if bindings.get("midi_resonance") is not None:
                    midi.resonance(int(resolved["midi_resonance"]))
                else:
                    midi.resonance(0)

                if bindings.get("midi_reverb") is not None:
                    midi.reverb_send(int(resolved["midi_reverb"]))

                draw_music_panel(annotated, resolved, arp.snapshot(), clock.bpm)
            else:
                # ── Mac controller mode — no MIDI output ──
                mac_ctrl.update(per_hand)
                # Small status card in the music-panel slot so the user
                # sees what mode they're in
                put_text(annotated, "MAC CONTROLLER",
                         (annotated.shape[1] - 260, 30),
                         scale=0.8, colour=(120, 120, 240), thickness=2)
                put_text(annotated, mac_ctrl.status(),
                         (annotated.shape[1] - 260, 56),
                         scale=0.45, colour=(230, 230, 230))

            # Always-on UI
            draw_both_feature_panels(annotated, per_hand)
            draw_beat_indicator(annotated, clock.step_number)
            draw_footer(annotated, midi.port_name)

            cv2.imshow(config.WINDOW_NAME, annotated)
            cv2.imshow(MENU_WINDOW_NAME, menu.draw())

            if cv2.getWindowProperty(
                config.WINDOW_NAME, cv2.WND_PROP_VISIBLE
            ) < 1:
                break

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            menu.handle_key(key)

    except KeyboardInterrupt:
        print("\n[Info] Interrupted.")

    finally:
        print("[Info] Shutting down...")
        clock.stop()
        note_manager.panic()
        midi.close()
        try:
            cap.release()
            tracker.close()
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("Bye.")


if __name__ == "__main__":
    main()
