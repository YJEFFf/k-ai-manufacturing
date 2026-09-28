"""평가관 01 사이클2 3회차 — 정상 운전 상태 전환을 기록 안에 넣으면 동결 모델이 경보하는가(검증전략 공백 확인용).

배경: 대회 정상 자료는 기록 안에 상태 전환이 0/469이다(전환은 모두 기록 공백에서 일어난다). 따라서 모델은 정상 상태 전환
(부하 ↔ 저수준, 전류 진폭 약 1.75배)을 학습·보정·평가 어디에서도 본 적이 없다. 연속 수집이면 약 10초마다 이런 전환이 들어온다.

방법(모델·문턱은 동결 그대로, 읽기 전용):
  - 같은 평가 구간의 50행 정상 기록 두 개를 이어 50행 합성 기록을 만든다. 앞 25행은 기록 r1의 0~24행, 뒤 25행은 기록 r2의 o~o+24행.
    o(0~16)는 0.6 Hz 전류 위상이 이음매에서 가장 잘 이어지게 고르고, r2 전류는 r1 평균에 맞춘다(인위적 직류 단차 없음).
  - 상태 전환(저수준→부하, 부하→저수준)과 대조(같은 상태끼리)를 같은 절차로 만든다. 대조가 이음매 자체의 효과를 잰다.
  - 합성 기록 사이에 5초 공백을 두고 한 파일로 만들어 GuardModel.predict(α)로 순차 추론한다(모델이 기록을 나눈다).
  - 이음매 뒤(25~49행)와 이음매 뒤 2초(25~44행) 안 경보가 있는 합성 기록의 비율을 센다. 이음매 앞(0~24행)은 원래 기록과 같다.
결과는 이 폴더의 judge01_transition_stress.json·.log에만 쓴다.

  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      yejun/analysis/press_rubric_review/cycle2/round3/judge01_transition_stress.py
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
ZIP = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "Dataset_소성가공 예지보전 AI 데이터셋.zip"
EVID = YEJUN / "analysis" / "press_evidence"
GUARD = YEJUN / "press_guard"
LOW, LOADED = "저수준", "부하"
K = 25
N_PAIRS = 200
REGIONS = {"B": (420, 600), "A": (480, 600)}
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s)


def main():
    t0 = time.monotonic()
    with zipfile.ZipFile(ZIP) as z:
        name = [m for m in z.namelist() if m.endswith("press_data_normal.csv")][0]
        n = pd.read_csv(io.BytesIO(z.read(name)))
    t = pd.to_datetime(n.TimeStamp, format="%Y-%m-%d %H:%M:%S.%f")
    seg = np.cumsum((t.diff().dt.total_seconds() - 0.1).abs().gt(1e-6).fillna(False).to_numpy())
    ost = pd.read_csv(EVID / "operating_states.csv").set_index("record")
    sys.path.insert(0, str(GUARD))
    from model import GuardModel  # noqa: E402
    rows_of = {s: np.flatnonzero(seg == s) for s in np.unique(seg)}
    R = {"k_splice_row": K, "pairs_per_condition": N_PAIRS}
    rng = np.random.default_rng(20260928)
    for sid, (lo, hi) in REGIONS.items():
        model = GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json")
        pool = {st: [s for s in ost.index if lo <= s < hi and ost.loc[s, "length"] == 50 and ost.loc[s, "state"] == st] for st in (LOW, LOADED)}
        log(f"[{sid}] 평가 구간 {lo}~{hi - 1}의 50행 기록: 저수준 {len(pool[LOW])}, 부하 {len(pool[LOADED])}")
        conds = {"저수준→부하": (LOW, LOADED), "부하→저수준": (LOADED, LOW), "저수준→저수준(대조)": (LOW, LOW), "부하→부하(대조)": (LOADED, LOADED)}
        frames, meta = [], []
        clock = pd.Timestamp("2030-01-01 00:00:00")
        for cname, (s1, s2) in conds.items():
            for _ in range(N_PAIRS):
                r1 = int(rng.choice(pool[s1]))
                r2 = int(rng.choice([r for r in pool[s2] if r != r1]))
                x1, x2 = n.iloc[rows_of[r1]].reset_index(drop=True), n.iloc[rows_of[r2]].reset_index(drop=True)
                c1 = x1.AI2_Current.to_numpy(float)
                c2 = x2.AI2_Current.to_numpy(float)
                # r1의 K행 위상과 r2의 o행 위상을 맞춘다(사인 적합: a sin + b cos, 위상 = atan2(b, a) + ωt)
                tt = np.arange(50) * .1
                A = np.column_stack([np.sin(2 * np.pi * .6 * tt), np.cos(2 * np.pi * .6 * tt), np.ones(50)])
                a1 = np.linalg.lstsq(A, c1, rcond=None)[0]
                a2 = np.linalg.lstsq(A, c2, rcond=None)[0]
                ph1 = np.arctan2(a1[1], a1[0]) + 2 * np.pi * .6 * K * .1
                best, bo = 9.0, 0
                for o in range(0, 17):
                    ph2 = np.arctan2(a2[1], a2[0]) + 2 * np.pi * .6 * o * .1
                    d = abs(np.angle(np.exp(1j * (ph2 - ph1))))
                    if d < best:
                        best, bo = d, o
                part2 = x2.iloc[bo:bo + (50 - K)].copy()
                part2["AI2_Current"] = part2.AI2_Current - a2[2] + a1[2]
                syn = pd.concat([x1.iloc[:K], part2], ignore_index=True)
                syn["TimeStamp"] = [(clock + pd.Timedelta(milliseconds=100 * i)).strftime("%Y-%m-%d %H:%M:%S.%f") for i in range(50)]
                clock += pd.Timedelta(seconds=5 + 4.9)
                frames.append(syn[["TimeStamp", "AI0_Vibration", "AI1_Vibration", "AI2_Current"]])
                amp_ratio = float(ost.loc[r2, "amp06"] / ost.loc[r1, "amp06"])
                meta.append(dict(cond=cname, r1=r1, r2=r2, offset=bo, phase_mismatch_deg=float(np.degrees(best)), amp_ratio=amp_ratio))
        # 이음매 없는 변형: 한 기록 안에서 K행부터 R행에 걸쳐 전류·진동 편차에 이득을 선형으로 준다(R=1 계단, 10 = 1초, 20 = 2초 경사).
        # 저수준→부하 이득은 상태 중앙값 비(전류 진폭·AI0 SD·AI1 SD), 부하→저수준은 그 역수. 위상 불연속이 없다.
        gains = {LOW: (ost[ost.state == LOADED].amp06.median() / ost[ost.state == LOW].amp06.median(),
                       ost[ost.state == LOADED].AI0_sd.median() / ost[ost.state == LOW].AI0_sd.median(),
                       ost[ost.state == LOADED].AI1_sd.median() / ost[ost.state == LOW].AI1_sd.median())}
        gains[LOADED] = tuple(1 / g for g in gains[LOW])
        R.setdefault("ramp_gains", {k: [float(x) for x in v] for k, v in gains.items()})
        for st in (LOW, LOADED):
            for ramp in (1, 10, 20):
                for r1 in pool[st]:
                    x1 = n.iloc[rows_of[r1]].reset_index(drop=True).copy()
                    w_ = np.clip((np.arange(50) - K + 1) / ramp, 0, 1)
                    for col, g in zip(("AI2_Current", "AI0_Vibration", "AI1_Vibration"), gains[st]):
                        v = x1[col].to_numpy(float)
                        m_ = v.mean()
                        x1[col] = m_ + (v - m_) * (1 + (g - 1) * w_)
                    x1["TimeStamp"] = [(clock + pd.Timedelta(milliseconds=100 * i)).strftime("%Y-%m-%d %H:%M:%S.%f") for i in range(50)]
                    clock += pd.Timedelta(seconds=5 + 4.9)
                    frames.append(x1[["TimeStamp", "AI0_Vibration", "AI1_Vibration", "AI2_Current"]])
                    meta.append(dict(cond=f"이득 {'저수준→부하' if st == LOW else '부하→저수준'} 경사 {ramp}행", r1=r1, r2=r1, offset=0,
                                     phase_mismatch_deg=0.0, amp_ratio=float(gains[st][0])))
        big = pd.concat(frames, ignore_index=True)
        res = {}
        for alpha in (.01, .03, .05):
            pr = model.predict(big, alpha)
            assert pr.record_id.nunique() == len(meta), (pr.record_id.nunique(), len(meta))
            al = pr.alarm.to_numpy().reshape(len(meta), 50)
            reason = pr.reason.to_numpy().reshape(len(meta), 50)
            df = pd.DataFrame(meta)
            df["pre"] = al[:, :K].any(1)
            df["post"] = al[:, K:].any(1)
            df["post2s"] = al[:, K:K + 20].any(1)
            df["first_post_reason"] = [next((reason[i, j] for j in range(K, 50) if al[i, j]), "") for i in range(len(meta))]
            g = df.groupby("cond", sort=False)
            res[alpha] = {c: dict(pre=float(x.pre.mean()), post=float(x.post.mean()), post2s=float(x.post2s.mean()),
                                  mismatch_deg_median=float(x.phase_mismatch_deg.median()),
                                  reasons=x.loc[x.post, "first_post_reason"].value_counts().to_dict()) for c, x in g}
            log(f"[{sid}] α={alpha}: " + "; ".join(f"{c} 앞 {v['pre']:.1%} 뒤 {v['post']:.1%} 뒤2초 {v['post2s']:.1%}" for c, v in res[alpha].items()))
            if alpha == .01:
                log(f"[{sid}] α=1% 이음매 뒤 첫 경보 근거: " + "; ".join(f"{c} {v['reasons']}" for c, v in res[alpha].items()))
                # 같은 상태끼리 이은 대조를 두 기록의 0.6 Hz 진폭 비로 층화(부하 쪽 하위 수준 차이가 원인인지)
                ctl = df[df.cond.str.contains("대조")].copy()
                ctl["log_ratio"] = np.abs(np.log(ctl.amp_ratio))
                ctl["ratio_bin"] = pd.cut(ctl.log_ratio, [0, np.log(1.1), np.log(1.3), np.log(1.6), 10], right=False,
                                          labels=["<1.1배", "1.1~1.3배", "1.3~1.6배", "≥1.6배"])
                strat = ctl.groupby("ratio_bin", observed=False).post.agg(["mean", "size"])
                res["control_by_amp_ratio"] = {str(k): dict(rate=float(v["mean"]) if v["size"] else None, n=int(v["size"])) for k, v in strat.iterrows()}
                parts = []
                for k, v in res["control_by_amp_ratio"].items():
                    rate = "없음" if v["rate"] is None else f"{v['rate']:.1%}"
                    parts.append(f"{k} {rate}(n={v['n']})")
                log(f"[{sid}] α=1% 대조(같은 상태끼리)의 진폭 비별 이음매 뒤 경보: " + "; ".join(parts))
        R[sid] = dict(region=(lo, hi), pool={k: len(v) for k, v in pool.items()}, results=res)
    R["elapsed_s"] = time.monotonic() - t0
    (HERE / "judge01_transition_stress.json").write_text(json.dumps(R, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    LOG.append(f"wrote judge01_transition_stress.json ({R['elapsed_s']:.1f}s)")
    (HERE / "judge01_transition_stress.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(LOG[-1])


if __name__ == "__main__":
    main()
