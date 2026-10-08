"""2단계(초기 탐색): 예준 v2의 오답을 원인별로 나누고, 원인별 수정을 얹어 다시 채점한다(보고서 2.3절 R1·R2 착안, 6장 초기 탐색 기록).

입력: v2_predictions/test_predictions_{A,B}.csv, 팀 레포에서 `python yejun/press_guard/train.py --out <폴더>`로 재현한 행별 예측
      (F1 A 0.961938·B 0.970990 재현 확인)
출력(outputs/): metrics_fixed.csv(변형별 F1), error_anatomy.json(오답 해부), predictions_fixed_{A,B}.csv(α 1% 행별 예측)
실행: cd code/press/cases && python 02_error_fix_score.py
보고서의 R1 사건 지속·R2 교차 확인이 여기서 처음 나왔다. v2 오답을 본 뒤 만든 사후 규칙이라 새 고장에서 성능이 나온다는 근거는 아니다.
"""
import json

import numpy as np
import pandas as pd

from common import OUT, SPLITS, load_both, prefix_r2

PRED = OUT.parent / "v2_predictions"
GAP_S = 60.0       # 사건 지속: 직전 기록이 이 시간 안에 끝났을 때만 이어받는다
CONFIRM_ROWS = 2   # 기록 안 경보가 이만큼이면 '확인된 이상'
R2_Q = 0.005       # 교차 확인: 정상 학습 기록 prefix R²의 0.5% 분위 이상이면 파형 정상
ALPHAS = (0.01, 0.03, 0.05)


def f1(y, a):
    """행 단위 TP·FP·FN·F1."""
    tp = int((a & y).sum()); fp = int((a & ~y).sum()); fn = int((~a & y).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)


def attach_prefix(pred: pd.DataFrame, raw: pd.DataFrame, r2: np.ndarray) -> pd.Series:
    """원자료 행별 prefix R²를 예측 파일 행에 시각(밀리초 문자열)으로 맞춰 붙인다."""
    key = pd.Series(r2, index=pd.to_datetime(raw.TimeStamp).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
    key = key[~key.index.duplicated()]  # 원자료에 같은 시각 중복 행이 있다. 첫 행 값을 쓴다
    return pred.timestamp.map(key)


def stream(df: pd.DataFrame, own: np.ndarray, wave_ok: np.ndarray, use_latch: bool, release: bool):
    """한 수집 흐름(정상 평가 또는 이상 파일)을 시간순으로 돌며 사건 지속(R1)을 적용한다.

    release=True면 이어받은 경보는 새 기록의 전류 파형이 정상으로 확인되는 행(8행째 이후 prefix R² ≥ 기준)에서 풀린다.
    반환: (행 경보, 기록별 '이어받은 경보가 끝까지 안 풀림')
    """
    ts = pd.to_datetime(df.timestamp).to_numpy()
    rec = df.record_id.to_numpy()
    alarm = own.copy()
    unreleased = {}
    prev_end, prev_confirmed = None, False
    for r in pd.unique(rec):
        idx = np.flatnonzero(rec == r)
        # 직전 기록의 판정만 보므로 실시간으로 할 수 있다. 첫 기록은 prev_confirmed가 False라 prev_end를 보지 않는다
        on = use_latch and prev_confirmed and (ts[idx[0]] - prev_end) / np.timedelta64(1, "s") <= GAP_S
        if on:
            for i in idx:
                if release and wave_ok[i]:
                    on = False
                    break
                alarm[i] = True
        unreleased[r] = bool(on)
        # 다음 기록으로 넘길 '확인된 이상': 자기 경보 2행 이상, 또는 이어받은 경보가 끝까지 안 풀림
        prev_confirmed = own[idx].sum() >= CONFIRM_ROWS or (release and bool(on))
        prev_end = ts[idx[-1]]
    return alarm, unreleased


def record_level(df: pd.DataFrame, own: np.ndarray, unreleased: dict) -> np.ndarray:
    """기록 단위 판정: 기록이 끝나면(최대 5초 뒤) 자기 경보 2행 이상이거나 이어받은 경보가 안 풀린 기록 전체를 이상으로 본다."""
    rec = df.record_id.to_numpy()
    hit = pd.Series(own.astype(int)).groupby(rec).transform("sum").to_numpy() >= CONFIRM_ROWS
    return hit | np.array([unreleased[r] for r in rec])


def main():
    normal, abnormal = load_both()
    r2n, r2a = prefix_r2(normal), prefix_r2(abnormal)
    rows, anatomy = [], {}
    for s, (train_end, _) in SPLITS.items():
        p = pd.read_csv(PRED / f"test_predictions_{s}.csv")
        # 예측 파일은 정상 평가 행 다음에 이상 행 순서다
        p["prefix_r2"] = np.r_[attach_prefix(p[p.subset == "normal_test"], normal, r2n).to_numpy(),
                               attach_prefix(p[p.subset == "abnormal"], abnormal, r2a).to_numpy()]
        r2_ref = np.nanquantile(r2n[normal.rec.to_numpy() < train_end], R2_Q)  # 정상 학습 기록만으로 정한다
        assert (p.alarm.to_numpy() == (p.p_value <= 0.01).to_numpy()).all()  # v2 경보 = p ≤ 1% 인지 확인
        y_all = p.label.to_numpy() == 1

        # 오답 해부 (α 1%). 미탐은 기록 시작 직후(과거 행이 없어 파형·예측오차 성분이 없음), 오경보는 고부하 정상의 진동 크기 단독
        miss = p[(p.subset == "abnormal") & (p.alarm == 0)]
        fa = p[(p.subset == "normal_test") & (p.alarm == 1)]
        anatomy[s] = dict(
            missed_rows=len(miss),
            missed_by_position={str(k): int(v) for k, v in miss.groupby("position").size().items()},
            missed_with_only_magnitude_available=int(miss.g_waveform.isna().sum()),  # 파형 성분이 아직 없는 기록 앞부분
            missed_records_low_vibration=sorted(miss[miss.magnitude < 2].record_id.unique().tolist()),
            false_alarm_rows=fa[["record_id", "position", "score", "reason", "prefix_r2"]].round(4).to_dict("records"),
            prefix_r2_reference=float(r2_ref),
        )

        # 교차 확인(R2): 크기 성분 단독 경보인데 그 행까지 전류 파형이 정상이면 보류한다
        mag_only = p.reason.fillna("").eq("magnitude").to_numpy()
        wave_ok = (p.prefix_r2 >= r2_ref).to_numpy()  # NaN(8행 미만)은 False → 보류하지 않음(안전 쪽)
        for alpha in ALPHAS:
            v2 = (p.p_value <= alpha).to_numpy()
            corroborated = v2 & ~(mag_only & wave_ok)
            variants = {"v2 (예준)": (v2, False, False), "+교차 확인": (corroborated, False, False),
                        "+사건 지속": (v2, True, False), "+교차 확인+사건 지속": (corroborated, True, False),
                        "+교차 확인+사건 지속(파형 정상 시 해제)": (corroborated, True, True)}
            for name, (own, latch, rel) in variants.items():
                out = np.zeros(len(p), bool)
                rl = np.zeros(len(p), bool)
                for sub in ("normal_test", "abnormal"):  # 사건 지속은 흐름 안에서만 이어진다
                    m = (p.subset == sub).to_numpy()
                    out[m], unrel = stream(p[m], own[m], wave_ok[m], latch, rel)
                    rl[m] = record_level(p[m], own[m], unrel)
                # 실시간 = 그 행까지의 정보로만 판정(v2와 같은 조건). 기록 단위 판정은 교차 확인+사건 지속 조합에만 낸다
                rows.append(dict(split=s, alpha=alpha, mode="실시간", variant=name, **f1(y_all, out)))
                if latch and own is corroborated:
                    rows.append(dict(split=s, alpha=alpha, mode="기록 단위", variant=name, **f1(y_all, rl)))
                if name.endswith("(파형 정상 시 해제)") and alpha == 0.01:
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
