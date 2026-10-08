"""사후(10/5, 팀 제안): 이상 기록 21개의 양상을 나눠 '먼저 점검할 곳'과 잇는다. 탐지·선택에는 쓰지 않는다.

기록마다 상부·하부 진동 크기(기록 안 SD), 전류 파형(사인 적합 R²), 전류 치우침(|평균|/진폭), 상·하부 상관이
정상 기록(10행 이상)의 0.5~99.5% 범위를 벗어났는지 표시하고 진동 쪽 표시로 세 양상으로 묶는다.
- 상·하부 진동 모두 큼 / 상부 진동만 큼 / 진동은 정상이거나 작고 전류만 이상
- 10행 미만 기록은 특징이 불안정해 '판단 보류'로 둔다
21기록은 한 사건(약 3분)의 연속 구간이라, 이 묶음은 고장 종류가 아니라 사건 안 시기별 양상이다.
입력: code/press/cases/outputs/case_features_{normal,abnormal}.csv (cases/01)
출력: outputs/07_anomaly_patterns.csv, outputs/07_anomaly_patterns.json
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CASES = HERE.parent / "cases" / "outputs"
OUT = HERE / "outputs"
MIN_ROWS = 10          # 보고서 1.6·2.1절과 같은 기준(10행 이상 기록)
LO, HI = 0.005, 0.995  # 정상 범위 = 정상 기록 분포의 0.5~99.5%


def main():
    normal = pd.read_csv(CASES / "case_features_normal.csv").query("n >= @MIN_ROWS")
    abn = pd.read_csv(CASES / "case_features_abnormal.csv")
    q = normal[["vib_upper_sd", "vib_lower_sd", "upper_lower_corr", "cur_sine_r2"]].quantile([LO, HI])
    off_hi = normal.cur_offset_ratio.abs().quantile(HI)
    rows = []
    for r in abn.itertuples():
        f = dict(upper_high=r.vib_upper_sd > q.vib_upper_sd[HI], upper_low=r.vib_upper_sd < q.vib_upper_sd[LO],
                 lower_high=r.vib_lower_sd > q.vib_lower_sd[HI], lower_low=r.vib_lower_sd < q.vib_lower_sd[LO],
                 wave_broken=r.cur_sine_r2 < q.cur_sine_r2[LO], offset=abs(r.cur_offset_ratio) > off_hi,
                 corr_negative=r.upper_lower_corr < q.upper_lower_corr[LO])
        if r.n < MIN_ROWS:
            kind = "판단 보류(10행 미만)"
        elif f["upper_high"] and f["lower_high"]:
            kind = "상·하부 진동 모두 큼"
        elif f["upper_high"]:
            kind = "상부 진동만 큼"
        elif not f["upper_high"] and not f["lower_high"] and (f["wave_broken"] or f["offset"]):
            kind = "진동 정상·작음, 전류만 이상"
        else:
            kind = "기타"
        rows.append(dict(rec=r.rec, n=r.n, t0=r.t0, kind=kind, **f))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "07_anomaly_patterns.csv", index=False)
    judged = d[d.n >= MIN_ROWS]
    summary = dict(min_rows=MIN_ROWS, normal_records=int(len(normal)),
                   counts={k: int(v) for k, v in d.kind.value_counts().items()},
                   records={k: g.rec.tolist() for k, g in d.groupby("kind")},
                   wave_broken_share=float(judged.wave_broken.mean()), offset_share=float(judged.offset.mean()))
    (OUT / "07_anomaly_patterns.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(d.to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
