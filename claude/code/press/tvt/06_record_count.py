"""6단계(사후, test 채점 이후): 기록 하나를 1개로 센 F1. 선택·잠금·최종 선정에는 쓰지 않는다.

보고서 2.4절 표의 '기록 판정 F1'은 기록 판정을 그 기록의 모든 행에 펼쳐 행으로 센 값이라 긴 기록일수록 비중이 크다.
여기서는 같은 판정을 (subset, 기록)마다 하나로 묶어 다시 센다. 모델·문턱·판정은 evalcore를 고치지 않고 그대로 쓴다.
대상(α 1%): 보고서 표의 evalcore 모델 12개. PCA·CUSUM·EWMA는 domain/03·04의 점수라 범위 밖이다.
출력: outputs/tvt_record_count.csv
실행: python code/press/tvt/06_record_count.py
"""
import json
import math

import pandas as pd

from evalcore import candidates, predict_rows
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, sha256_file

MODELS = ["iforest", "lstm20", "maxz3", "knn5", "mlp_ae5", "v1", "v2", "v2+C1d1", "v3_B3k10", "v3_C2d1", "v2+H1", "v2+H1+H2"]


def main():
    # 05와 같은 확인: 잠긴 선택 파일과 점수 캐시가 그대로일 때만 돈다
    sel = json.loads((OUT / "tvt_selection.json").read_text(encoding="utf-8"))
    if sha256_file(OUT / "tvt_selection.json") != (OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("선택 파일 해시 불일치")
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    cands = {c[0]: c for c in candidates(meta["A"]["complexity"])}
    table_f1 = {r: pd.read_csv(OUT / f"tvt_{r}.csv").query("mode == 'record'") for r in ("test", "valid")}
    rows = []
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        if sha256_file(CACHE / f"rows_{s}.pkl") != sel["inputs"]["rows_sha256"][s]:
            raise SystemExit("점수 캐시 해시 불일치")
        for regime in ("test", "valid"):
            for m in MODELS:
                p = predict_rows(t, cands[m], PRIMARY_ALPHA, regime, meta[s]["r2_ref"])
                # 행으로 센 값이 표와 같아야 같은 판정을 묶었다고 할 수 있다(정의 확인)
                by_row = f1_counts(p.label.to_numpy() == 1, p.alarm_record.to_numpy().astype(bool))
                ref = table_f1[regime].query("split == @s and model == @m and alpha == @PRIMARY_ALPHA").f1
                if len(ref) != 1 or not math.isclose(by_row["f1"], float(ref.iloc[0]), abs_tol=1e-9):
                    raise SystemExit(f"행 가중 F1이 tvt_{regime}.csv와 다름: {s} {m}")
                rec = p.groupby(["subset", "rec"]).agg(y=("label", "max"), a=("alarm_record", "max"))
                by_rec = f1_counts(rec.y.to_numpy() == 1, rec.a.to_numpy() == 1)
                rows.append(dict(split=s, regime=regime, model=m, rec_tp=by_rec["tp"], rec_fp=by_rec["fp"], rec_fn=by_rec["fn"],
                                 rec_f1=by_rec["f1"], row_weighted_f1=by_row["f1"]))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "tvt_record_count.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
