"""Frozen causal injections and explicit assumption-based sensor stress tests."""
from __future__ import annotations

import numpy as np

FAMILIES = {
    "vibration_noise": {"targets": [0, 1], "strengths": [.5, 1.0]},
    "vibration_impulse": {"targets": [0, 1], "strengths": [2.0, 4.0]},
    "vibration_amplification": {"targets": [0, 1], "strengths": [.5, 1.0]},
    "current_distortion": {"targets": [2], "strengths": [.5, 1.0]},
}
ONSETS = (.25, .60)
DEVELOPMENT_SEEDS = (101,)
EVALUATION_SEEDS = (811, 1217, 2027)


class CausalGenerator:
    def fit(self, records):
        values = np.vstack(records)
        self.mean_ = values.mean(axis=0)
        self.std_ = values.std(axis=0)
        centered = np.vstack([r - r.mean(axis=0) for r in records])
        self.ac_scale_ = np.sqrt(np.mean(centered ** 2, axis=0))
        # Current distortion amplitude uses normal sine-fit residual RMS, with
        # the reference oscillator fixed before evaluation, not test-derived.
        errors = []
        for r in records:
            if len(r) < 8:
                continue
            t = np.arange(len(r))
            design = np.column_stack([np.ones(len(r)), np.sin(2 * np.pi * .06064 * t),
                                      np.cos(2 * np.pi * .06064 * t)])
            errors.extend(r[:, 2] - design @ np.linalg.lstsq(design, r[:, 2], rcond=None)[0])
        self.current_residual_scale_ = float(np.sqrt(np.mean(np.asarray(errors) ** 2)))
        return self

    def inject(self, record, family, target, strength, seed, onset):
        x = np.asarray(record, float)
        out = x.copy()
        if not 0 <= onset < len(x):
            raise ValueError("onset must be within the record")
        if target not in FAMILIES[family]["targets"]:
            raise ValueError("Unsupported target for injection family")
        if strength == 0:
            return out
        rng = np.random.default_rng(seed)
        k = np.arange(len(x) - onset)
        if family == "vibration_noise":
            delta = strength * self.ac_scale_[target] * rng.standard_normal(len(k))
        elif family == "vibration_impulse":
            delta = strength * self.ac_scale_[target] * np.exp(-k / 4.0) * np.cos(2 * np.pi * .3 * k)
        elif family == "vibration_amplification":
            # Frozen normal training center; no future record mean is used.
            delta = strength * (x[onset:, target] - self.mean_[target])
        else:
            delta = strength * self.current_residual_scale_ * (
                np.sin(2 * np.pi * .21 * k + rng.uniform(-np.pi, np.pi)) + .5 * rng.standard_normal(len(k)))
        out[onset:, target] += delta
        assert out[:onset].tobytes() == x[:onset].tobytes()
        return out

    def stress_specs(self):
        specs = []
        for target in range(3):
            for sign in (-1, 1):
                specs.append(dict(kind="offset", target=target, value=float(sign * self.std_[target]), seed=401))
            for value in (.8, 1.2):
                specs.append(dict(kind="gain", target=target, value=value, seed=401))
            specs.append(dict(kind="stuck", target=target, value=.5, seed=401))
        specs += [dict(kind="load", target=2, value=v, seed=401) for v in (.5, 1.5)]
        specs += [dict(kind="quantization", target=-1, value=4.0, seed=401)]
        specs += [dict(kind="jitter", target=2, value=v, seed=401) for v in (.0001, .0005)]
        return specs

    def perturb(self, records, kind, target, value, seed=401):
        out = []
        for record_id, record in enumerate(records):
            x = np.asarray(record, float).copy()
            if kind == "offset":
                x[:, target] += value
            elif kind == "gain":
                x[:, target] *= value
            elif kind == "load":
                x[:, 2] = self.mean_[2] + value * (x[:, 2] - self.mean_[2])
            elif kind == "stuck":
                onset = min(len(x) - 1, max(1, int(len(x) * value)))
                x[onset:, target] = x[max(0, onset - 1), target]
            elif kind == "quantization":
                step = np.array([1e-4, 1e-4, 1.1920929]) * value
                x = np.round(x / step) * step
            elif kind == "jitter":
                # Assumed 60.6-Hz physical carrier aliased to the observed
                # .6064-Hz waveform; retrospective nuisance, not sensor spec.
                t = np.arange(len(x))
                basis = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * .06064 * t), np.cos(2 * np.pi * .06064 * t)])
                coef = np.linalg.lstsq(basis, x[:, 2], rcond=None)[0]
                epsilon = np.random.default_rng(seed + record_id).normal(0, value, len(x))
                angle = 2 * np.pi * .06064 * t + 2 * np.pi * 60.6 * epsilon
                x[:, 2] += (coef[1] * np.sin(angle) + coef[2] * np.cos(angle)
                             - basis[:, 1:] @ coef[1:])
            else:
                raise ValueError(kind)
            out.append(x)
        return out
