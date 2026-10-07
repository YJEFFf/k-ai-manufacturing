"""9단계(사후, test 채점 이후): v2 세 성분의 몫을 인공 고장 주입으로 가른다(보고서 2.4절 †). 선택·잠금·최종 선정에는 쓰지 않는다.

실제 이상 사건은 어느 모델로도 1.000 근처라 성분의 몫이 드러나지 않는다(2.4절). 그래서 04와 같은 주입(예준 v3 Generator,
seed 11·29·47)을 test 정상 기록에 하나씩 넣고, v2의 성분 조합마다 경보가 나는지 본다.
- 조합: 크기만 / 파형만 / 동역학만 / 크기+파형 / v2(세 성분). 조합 점수 = 고른 성분 꼬리 점수의 최댓값(v2와 같은 결합)
- 문턱: 조합마다 정상 valid(보정) 기록의 최대 점수로 conformal 문턱을 다시 잡는다(α 1%, v2와 같은 보정 단위)
- 규칙(R1·R2)은 붙이지 않는다. 한 기록의 탐지력만 본다. 강도 0은 주입 없는 대조(정상 기록 경보율)
- 확인: 세 성분 조합의 탐지는 04의 v2 결과(validation_v1.csv)와 같아야 한다
출력: outputs/ablation_injection.csv(기록별), outputs/ablation_pod.csv(조건별 탐지율), outputs/ablation_summary.json
실행: python code/press/tvt/09_component_ablation.py --repo <팀 레포>
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lib import OUT, SPLITS, ns_time, repo_arg, setup, v3_records

_spec = importlib.util.spec_from_file_location("tvt_v04", Path(__file__).with_name("04_validation.py"))
V04 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V04)

ALPHA = V04.ALPHA
SUBSETS = {"크기": ("g_magnitude",), "파형": ("g_waveform",), "동역학": ("g_dynamics",),
           "크기+파형": ("g_magnitude", "g_waveform"), "v2": ("g_magnitude", "g_waveform", "g_dynamics")}


def subset_scores(comp):
    """성분 조합별 행 점수(고른 성분 꼬리 점수의 최댓값)."""
    out = {}
    for name, keys in SUBSETS.items():
        s = comp[keys[0]]
        for k in keys[1:]:
            s = np.fmax(s, comp[k])
        out[name] = s
    return out


class Ablation:
    """v2 학습 결과 하나로 성분 조합별 문턱을 정하고, 프레임마다 조합별 행 경보를 낸다."""

    def __init__(self, M, fin, cal_frame):
        self.M, self.fin = M, fin
        D, guard = M["D"], M["guard"]
        cf = D.quantize(D.inputs_only(cal_frame), "matched")
        sg = guard.layout(cf)[1]
        units = guard.alert_units(sg, D.segment_positions(sg)[0])
        scores = subset_scores(fin.model.components(cf, sg))
        self.cal = {k: M["segment_max"](v, units) for k, v in scores.items()}
        # 세 성분 조합의 문턱은 v2 학습 때 정한 보정값과 같아야 한다
        if not np.allclose(np.sort(self.cal["v2"]), np.sort(fin.model.cal)):
            raise SystemExit("v2 보정값 재계산 불일치")

    def alarms(self, frame):
        D, guard, cp = self.M["D"], self.M["guard"], self.M["conformal_p"]
        frame = frame.reset_index(drop=True)
        _, seg = guard.layout(frame)
        q = D.quantize(D.inputs_only(frame), "matched")
        scores = subset_scores(self.fin.model.components(q, seg))
        pos = D.segment_positions(seg)[0]
        out = {}
        for k, s in scores.items():
            p = cp(self.cal[k], s)
            out[k] = np.isfinite(p) & (p <= ALPHA)
        return out, pos


def injected(ab, frame, recs, k, x_new, onset):
    """기록 k를 x_new로 바꾸고 직전 기록과 함께 흘려(04와 같은 방식) 기록 k에서 주입 뒤 경보가 났는지 본다."""
    S = ab.M["D"].SENSORS
    idx = recs[k]
    parts = ([recs[k - 1]] if k > 0 else []) + [idx]
    sub = frame.iloc[np.concatenate(parts)].reset_index(drop=True).copy()
    sub.loc[len(sub) - len(idx):, S] = x_new
    alarms, pos = ab.alarms(sub)
    mine = np.arange(len(sub)) >= len(sub) - len(idx)
    after = pos[mine] >= max(onset, 0)
    return {k2: bool((a[mine] & after).any()) for k2, a in alarms.items()}


def run_split(M, normal, sid):
    D, v3 = M["D"], M["v3"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    fin = V04.fit_split(M, sp["train"], sp["cal"])
    ab = Ablation(M, fin, sp["cal"])
    q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
    gen = v3.Generator(v3.features(v3_records(M, q_tr, "train")), sid)
    test = sp["test"].reset_index(drop=True)
    recs = V04.records_of(test, M)
    X = test[D.SENSORS].to_numpy(float)
    f_test = v3.features([V04.v3_record(M, X[idx], k) for k, idx in enumerate(recs)])
    rows = []
    for fam, strengths in V04.SELECTION.items():
        for target in V04.TARGETS[fam]:
            axis = f"v{target}_rms" if target < 2 else "i_residual"
            scale = gen.scales(f_test, axis)
            for strength in (0.0,) + strengths:
                for seed in (V04.SEEDS if strength > 0 else V04.SEEDS[:1]):
                    for k, idx in enumerate(recs):
                        rec, info = gen.inject(V04.v3_record(M, X[idx], k), fam, target, strength, seed, scale[k])
                        if strength > 0 and not info["valid"]:   # 04와 같이 주입기가 미지원으로 둔 기록은 미탐으로 센다
                            rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k,
                                             supported=False, **{k2: False for k2 in SUBSETS}))
                            continue
                        res = injected(ab, test, recs, k, rec.x, info["onset"])
                        rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k, supported=True, **res))
    return pd.DataFrame(rows)


def main():
    repo = repo_arg()
    M = setup(repo)
    normal, _, _ = M["D"].load(repo / "yejun/press_submission")
    t = pd.concat([run_split(M, normal, s) for s in SPLITS], ignore_index=True)
    t.to_csv(OUT / "ablation_injection.csv", index=False)
    # 확인: 세 성분 조합 = 04의 v2 탐지(미지원 주입은 둘 다 미탐)
    ref = pd.read_csv(OUT / "validation_v1.csv")
    key = ["split", "family", "target", "strength", "seed", "record"]
    m = t.merge(ref[key + ["v2|detected"]], on=key, how="inner")
    if len(m) != len(t) or (m["v2"] != m["v2|detected"]).any():
        raise SystemExit(f"v2 조합이 04 결과와 다름: {len(m)} / {len(t)}, 불일치 {(m['v2'] != m['v2|detected']).sum()}")
    pod = t.groupby(["split", "family", "target", "strength"])[list(SUBSETS)].mean().round(4).reset_index()
    pod.to_csv(OUT / "ablation_pod.csv", index=False)
    # 요약: 계열별(전류 파형 주입 / 진동 주입) 강도별 평균 탐지율, 주입 없는 대조의 경보율
    t["kind"] = np.where(t.family == "current_residual", "전류 파형 주입", "진동 단독 주입")
    summ = {}
    for (kind, strength), g in t.groupby(["kind", "strength"]):
        summ[f"{kind}|{strength}"] = {k: round(float(g[k].mean()), 4) for k in SUBSETS}
    ctrl = t[t.strength == 0].drop_duplicates(["split", "record"])
    summ["대조(주입 없음)"] = {k: round(float(ctrl[k].mean()), 4) for k in SUBSETS}
    summ["n_records_per_split"] = ctrl.groupby("split").size().to_dict()
    (OUT / "ablation_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    print(pod.to_string(index=False))


if __name__ == "__main__":
    main()
