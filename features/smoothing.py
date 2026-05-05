# ─────────────────────────────────────────────
#  features/smoothing.py
#  Exponential moving average for every feature,
#  so raw jitter doesn't flicker the musical output.
# ─────────────────────────────────────────────

from typing import Optional
import config


class FeatureSmoother:
    """Apply EMA (exponential moving average) to each feature."""

    def __init__(self, alpha: Optional[float] = None):
        self._alpha = config.EMA_ALPHA if alpha is None else alpha
        self._state: dict = {}

    def smooth(self, features: Optional[dict]) -> Optional[dict]:
        if features is None:
            # Don't reset — keep last known smoothed values so note_off
            # logic elsewhere doesn't flicker. But return None so callers
            # know there's no live hand.
            return None

        a = self._alpha
        out = {}
        for k, v in features.items():
            if k in self._state:
                self._state[k] = a * v + (1.0 - a) * self._state[k]
            else:
                self._state[k] = v
            out[k] = self._state[k]
        return out

    def reset(self):
        self._state.clear()


class MultiHandSmoother:
    """
    One FeatureSmoother per hand. Input/output shape matches
    MultiHandExtractor.
    """

    def __init__(self, alpha: Optional[float] = None):
        from vision.tracker import HANDS
        self._smoothers = {h: FeatureSmoother(alpha=alpha) for h in HANDS}

    def smooth(self, per_hand_features: dict) -> dict:
        return {
            hand: self._smoothers[hand].smooth(feats)
            for hand, feats in per_hand_features.items()
        }

    def reset(self):
        for s in self._smoothers.values():
            s.reset()
