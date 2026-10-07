"""Review probe (not part of the submission): normal-only apparent-frequency shift.

Split B: fit records 0-299, calibrate 300-419, evaluate normal test 420-599.
Each test record (>= MIN_LEN rows) is re-synthesised as best-fit sine at f+delta
plus the original residual, then re-quantised to the matched current grid.
delta = 0 is the re-synthesis control.  Abnormal data are never opened.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FRONTIER = HERE.parents[1]
REPO = HERE.parents[4]
sys.path.insert(0, str(FRONTIER))
sys.dont_write_bytecode = True
from run_experiment import load_records  # noqa: E402
from frontier_model import FrontierSuite  # noqa: E402

DATA = str(REPO / "데이터셋" / "3. 소성가공 예지보전 AI 데이터셋")
DT, STEP, MIN_LEN = 0.1, 1.1920929, 8
GRID = np.arange(0.30, 0.9001, 0.0005)


def fit_sine(x):
    t = np.arange(len(x)) * DT
    best = None
    for f in GRID:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(len(x))])
        coef, *_ = np.linalg.lstsq(A, x, rcond=None)
        sse = float(((x - A @ coef) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, f, coef)
    return best[1], best[2]


def shift(records, delta, cache):
    out = []
    for k, r in enumerate(records):
        r = r.copy()
        if len(r) >= MIN_LEN:
            if k not in cache:
                cache[k] = fit_sine(r[:, 2])
            f, (a, b, c) = cache[k]
            t = np.arange(len(r)) * DT
            fit = a * np.sin(2 * np.pi * f * t) + b * np.cos(2 * np.pi * f * t) + c
            resid = r[:, 2] - fit
            new = a * np.sin(2 * np.pi * (f + delta) * t) + b * np.cos(2 * np.pi * (f + delta) * t) + c + resid
            r[:, 2] = np.round(new / STEP) * STEP
        out.append(r)
    return out


def main():
    normal, _ = load_records(DATA, "normal")
    train, cal, test = normal[:300], normal[300:420], normal[420:]
    suite = FrontierSuite().fit(train).calibrate(cal)
    models = ["V2", "C", "W", "VD3", "V2+VD3@1"]
    cache, rows = {}, []
    base = suite.alarms(suite.score(test), .01)
    for model in models:
        rows.append(dict(delta_hz="original", model=model,
                         fp_records=int(sum(np.any(a) for a in base[model])), records=len(test)))
    for delta in (0.0, 0.005, -0.005, 0.01, -0.01, 0.02, -0.02, 0.05, -0.05, 0.1, -0.1):
        alarms = suite.alarms(suite.score(shift(test, delta, cache)), .01)
        for model in models:
            rows.append(dict(delta_hz=delta, model=model,
                             fp_records=int(sum(np.any(a) for a in alarms[model])), records=len(test)))
        print(delta, {m: rows[-len(models) + i]["fp_records"] for i, m in enumerate(models)}, flush=True)
    df = pd.DataFrame(rows)
    df["fp_rate"] = df.fp_records / df.records
    out = Path(__file__).with_name("freq_shift_probe.csv")
    df.to_csv(out, index=False)
    print(df.pivot(index="delta_hz", columns="model", values="fp_records").to_string())


if __name__ == "__main__":
    main()
