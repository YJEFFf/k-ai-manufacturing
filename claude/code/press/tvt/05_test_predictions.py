"""5단계: 시험(test) 행 단위 예측 파일과 최종 모델의 첫 경보 지연을 만든다(보고서 2.5절 첫 경보 지연, 6장 제출 예측 파일).

3단계와 같은 방식으로 선택 파일·점수 캐시 해시를 확인한 뒤 실행하고, 3단계 잠금 산출물은 건드리지 않는다.
대상(α 1%): 최종 v2+R1+R2(코드 v2+H1+H2), 잠금 선택 v2+R1(v2+H1), v2.
출력: outputs/test_predictions_{A,B}.csv, outputs/test_first_alarm.json(시험 이상 기록별 첫 경보까지의 시간)
실행: python code/press/tvt/05_test_predictions.py
"""
import json

import pandas as pd

from evalcore import candidates, predict_rows
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, sha256_file

MODELS = {"v2+H1+H2": "final_v2_R1_R2", "v2+H1": "locked_v2_R1", "v2": "v2"}  # 코드 이름 → 출력 열 이름(보고서 이름)


def main():
    sel = json.loads((OUT / "tvt_selection.json").read_text(encoding="utf-8"))
    if sha256_file(OUT / "tvt_selection.json") != (OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("선택 파일 해시 불일치")
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    cands = {c[0]: c for c in candidates(meta["A"]["complexity"])}
    delays = {}
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        if sha256_file(CACHE / f"rows_{s}.pkl") != sel["inputs"]["rows_sha256"][s]:
            raise SystemExit("점수 캐시 해시 불일치")
        # 모델별 예측을 행 키(subset·label·rec·pos·ts)로 옆으로 붙인다
        frames = []
        for name, col in MODELS.items():
            p = predict_rows(t, cands[name], PRIMARY_ALPHA, "test", meta[s]["r2_ref"])
            frames.append(p.rename(columns={"alarm_realtime": f"{col}_realtime", "alarm_record": f"{col}_record"}).drop(columns=["model", "alpha"]))
        out = frames[0]
        for f in frames[1:]:
            out = out.merge(f, on=["subset", "label", "rec", "pos", "ts"], how="left")
        out.to_csv(OUT / f"test_predictions_{s}.csv", index=False)
        # 3단계 결과와 같은지 확인용(최종 모델 실시간 F1)
        m = f1_counts(out.label.to_numpy() == 1, out.final_v2_R1_R2_realtime.to_numpy().astype(bool))
        ab = out[out.subset == "abnormal"]
        first = ab[ab.final_v2_R1_R2_realtime == 1].groupby("rec").pos.min() * 0.1  # 첫 경보 행 위치 × 0.1초
        delays[s] = dict(f1_check=m, records=int(ab.rec.nunique()), first_alarm_s_median=float(first.median()),
                         first_alarm_s_max=float(first.max()), records_alarm_at_first_row=int((first == 0).sum()))
    (OUT / "test_first_alarm.json").write_text(json.dumps(delays, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(delays, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
