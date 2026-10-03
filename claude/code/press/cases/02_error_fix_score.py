"""2단계: 예준 v2가 왜 틀렸는지 분해하고, 오답 원인별 수정을 얹어 다시 채점한다.

입력: v2_predictions/test_predictions_{A,B}.csv
      (예준 레포에서 `python yejun/press_guard/train.py --out <폴더>`로 재현한 행별 예측. F1 A 0.961938·B 0.970990 재현 확인)

오답 원인과 수정
1) 미탐: 기록이 막 시작된 행(위치 0~6)은 쓸 수 있는 과거 행이 없어 파형·예측오차 성분이 아직 계산되지 않는다.
   그런데 이상 기록 21개는 한 사건(3분)이 수집 공백(1.8~8.6초)으로 잘린 조각이다. v2는 기록마다 기억을 지운다.
   → 수정 '사건 지속': 직전 기록(60초 안)이 '확인된 이상'(교차 확인 후 경보 2행 이상)이면 새 기록은 첫 행부터 경보를 유지한다.
     직전 기록의 판정만 쓰므로 실시간으로 가능하다.
2) 오경보: 정상 고부하 기록에서 진동 크기 하나만 문턱을 넘었다(전류 파형은 완전 정상, 사인 R² 0.99 이상).
   → 수정 '교차 확인': 크기 성분 단독 경보인데 그 행까지의 전류 파형이 정상(정상 학습 기록 prefix R²의 0.5% 분위 이상)이면 경보를 보류한다.
     파형을 판단할 행(8행)이 아직 없으면 경보를 그대로 둔다(안전 쪽).

채점 방식
- 실시간: 행이 들어오는 순간 그 행까지의 정보로만 판정 (v2와 같은 조건)
- 기록 단위: 기록 하나가 끝나면(최대 5초 뒤) 그 기록 전체를 한 번에 판정해 모든 행에 같은 답을 준다

※ 두 수정 모두 v2의 오답을 본 뒤 만든 규칙이다. 같은 자료 안의 사후 개선이며 새 고장에서의 성능 근거가 아니다.
"""
import json

import numpy as np
import pandas as pd

from common import OUT, SPLITS, load_both, prefix_r2

PRED = OUT.parent / "v2_predictions"
GAP_S = 60.0
CONFIRM_ROWS = 2
R2_Q = 0.005
ALPHAS = (0.01, 0.03, 0.05)


def f1(y, a):
    tp = int((a & y).sum()); fp = int((a & ~y).sum()); fn = int((~a & y).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)


def attach_prefix(pred: pd.DataFrame, raw: pd.DataFrame, r2: np.ndarray) -> pd.Series:
    key = pd.Series(r2, index=pd.to_datetime(raw.TimeStamp).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
    key = key[~key.index.duplicated()]
    return pred.timestamp.map(key)


def stream(df: pd.DataFrame, own: np.ndarray, wave_ok: np.ndarray, use_latch: bool, release: bool):
    """한 수집 흐름(정상 평가 또는 이상 파일)을 시간순으로 돌며 사건 지속을 적용한다.

    release=True면 이어받은 경보는 새 기록의 전류 파형이 정상으로 확인되는 행(8행째 이후 prefix R² ≥ 기준)에서 풀린다.
    반환: 행 경보, 행마다 이어받은 경보가 켜져 있는지, 기록 끝까지 이어받은 경보가 안 풀렸는지(기록별)
    """
    ts = pd.to_datetime(df.timestamp).to_numpy()
    rec = df.record_id.to_numpy()
    alarm = own.copy()
    active = np.zeros(len(df), bool)
    unreleased = {}
    prev_end, prev_confirmed = None, False
    for r in pd.unique(rec):
        idx = np.flatnonzero(rec == r)
        start = ts[idx[0]]
        on = use_latch and prev_confirmed and prev_end is not None and (start - prev_end) / np.timedelta64(1, "s") <= GAP_S
        if on:
            for i in idx:
                if release and wave_ok[i]:
                    on = False
                    break
                active[i] = True
        alarm[idx] |= active[idx]
        unreleased[r] = bool(on)
        # 다음 기록으로 넘길 '확인된 이상': 자기 경보 2행 이상, 또는 이어받은 경보가 끝까지 안 풀림
        prev_confirmed = own[idx].sum() >= CONFIRM_ROWS or (release and bool(on))
        prev_end = ts[idx[-1]]
    return alarm, active, unreleased


def record_level(df: pd.DataFrame, own: np.ndarray, unreleased: dict) -> np.ndarray:
    """기록이 끝난 뒤 판정: '확인된 이상'(교차 확인 후 자기 경보 2행 이상)이거나, 이어받은 경보가 끝까지 안 풀렸으면 기록 전체가 이상."""
    rec = df.record_id.to_numpy()
    hit = pd.Series(own.astype(int)).groupby(rec).transform("sum").to_numpy() >= CONFIRM_ROWS
    return hit | np.array([unreleased[r] for r in rec])


def main():
    normal, abnormal = load_both()
    r2n, r2a = prefix_r2(normal), prefix_r2(abnormal)
    rows, anatomy = [], {}
    for s, (train_end, cal_end) in SPLITS.items():
        p = pd.read_csv(PRED / f"test_predictions_{s}.csv")
        p["prefix_r2"] = np.r_[attach_prefix(p[p.subset == "normal_test"], normal, r2n).to_numpy(),
                               attach_prefix(p[p.subset == "abnormal"], abnormal, r2a).to_numpy()]
        r2_ref = np.nanquantile(r2n[normal.rec.to_numpy() < train_end], R2_Q)
        assert (p.alarm.to_numpy() == (p.p_value <= 0.01).to_numpy()).all()
        y_all = p.label.to_numpy() == 1

        # 오답 해부 (α=1%)
        miss = p[(p.subset == "abnormal") & (p.alarm == 0)]
        fa = p[(p.subset == "normal_test") & (p.alarm == 1)]
        anatomy[s] = dict(
            missed_rows=len(miss),
            missed_by_position={str(k): int(v) for k, v in miss.groupby("position").size().items()},
            missed_with_only_magnitude_available=int(miss.g_waveform.isna().sum() if "g_waveform" in miss else 0),
            missed_records_low_vibration=sorted(miss[miss.magnitude < 2].record_id.unique().tolist()),
            false_alarm_rows=fa[["record_id", "position", "score", "reason", "prefix_r2"]].round(4).to_dict("records"),
            prefix_r2_reference=float(r2_ref),
        )

        for alpha in ALPHAS:
            v2 = (p.p_value <= alpha).to_numpy()
            mag_only = p.reason.fillna("").eq("magnitude").to_numpy()
            wave_ok = (p.prefix_r2 >= r2_ref).to_numpy()  # NaN(8행 미만)은 False → 보류하지 않음
            corroborated = v2 & ~(mag_only & wave_ok)
            variants = {"v2 (예준)": (v2, False, False), "+교차 확인": (corroborated, False, False),
                        "+사건 지속": (v2, True, False), "+교차 확인+사건 지속": (corroborated, True, False),
                        "+교차 확인+사건 지속(파형 정상 시 해제)": (corroborated, True, True)}
            for name, (own, latch, rel) in variants.items():
                out = np.zeros(len(p), bool)
                rl = np.zeros(len(p), bool)
                for sub in ("normal_test", "abnormal"):
                    m = (p.subset == sub).to_numpy()
                    out[m], _, unrel = stream(p[m], own[m], wave_ok[m], latch, rel)
                    rl[m] = record_level(p[m], own[m], unrel)
                rows.append(dict(split=s, alpha=alpha, mode="실시간", variant=name, **f1(y_all, out)))
                if latch and own is corroborated:
                    rows.append(dict(split=s, alpha=alpha, mode="기록 단위", variant=name, **f1(y_all, rl)))
                if name.endswith("(파형 정상 시 해제)"):
                    if alpha == 0.01:
                        keep = p[["subset", "label", "record_id", "position", "timestamp", "score", "p_value", "reason", "prefix_r2"]].copy()
                        keep["alarm_v2"] = v2.astype(int)
                        keep["alarm_realtime"] = out.astype(int)
                        keep["alarm_record_level"] = rl.astype(int)
                        keep.to_csv(OUT / f"predictions_fixed_{s}.csv", index=False)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "metrics_fixed.csv", index=False)
    (OUT / "error_anatomy.json").write_text(json.dumps(anatomy, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(json.dumps(anatomy, ensure_ascii=False, indent=1))
    print(res.round(6).to_string(index=False))


if __name__ == "__main__":
    main()
