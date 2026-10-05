"""8단계(10/5 추가): 기반 모델 v2 점수를 이상 확률로 바꿔 test 예측 파일에 붙인다. 경보·선택·잠금과는 무관하다.

팀 v2 확률 층(yejun/press_guard/probability.py의 ProbabilityCalibrator)을 그대로 쓰되 **valid 자료만으로** 맞춘다.
정상 valid 행(0)과 이상 valid 행(1)에 단조 회귀 → 우도비 → 사전 비율로 사후확률. test 행은 보정에 쓰지 않는다.
- 사전 비율 두 가지: 현장 가정 1%(운영 표시용), test 파일의 이상 행 비율(파일 라벨로 채점할 때)
- 평가: test 행 Brier 점수, 그리고 비율만 쓴 예측(상수 π)의 Brier
출력: outputs/test_predictions_{A,B}.csv에 확률 열 2개를 붙인다(경보 열은 그대로), outputs/tvt_probability.json
실행: python code/press/tvt/08_probability.py --repo <팀 레포>
"""
import json
import sys

import numpy as np
import pandas as pd

from lib import CACHE, OUT, SPLITS, repo_arg, sha256_file

SITE_PRIOR = 0.01
COLS = ["v2_prob_site1pct", "v2_prob_fileprior"]


def brier(y, p):
    return float(np.mean((np.asarray(p, float) - y) ** 2))


def main():
    sys.path.insert(0, str(repo_arg() / "yejun" / "press_guard"))
    from probability import ProbabilityCalibrator
    # 05와 같은 확인: 잠긴 선택 파일과 점수 캐시가 그대로일 때만 돈다
    sel = json.loads((OUT / "tvt_selection.json").read_text(encoding="utf-8"))
    if sha256_file(OUT / "tvt_selection.json") != (OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("선택 파일 해시 불일치")
    summary = {}
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        if sha256_file(CACHE / f"rows_{s}.pkl") != sel["inputs"]["rows_sha256"][s]:
            raise SystemExit("점수 캐시 해시 불일치")
        va, te = t[t.part == "valid"], t[t.part == "test"]
        units = va.loc[va.subset == "normal", "rec"].nunique()   # conformal 보정 단위 = 정상 valid 기록 수(LR 표시 상한 units+1)
        cal = ProbabilityCalibrator.fit(va.loc[va.subset == "normal", "v2|score"], va.loc[va.subset == "abnormal", "v2|score"],
                                        calibration_units=units, split=s, source=dict(fit="valid only"))
        y = (te.label.to_numpy() == 1).astype(float)
        pi_file = float(y.mean())
        score = te["v2|score"].to_numpy()
        p_site = np.round(cal.probability(score, prior=SITE_PRIOR), 6)   # 소수 6자리: OS마다 끝자리가 달라지지 않게
        p_file = np.round(cal.probability(score, prior=pi_file), 6)
        summary[s] = dict(calibration_units=int(units), fit_normal_rows=int((va.subset == "normal").sum()),
                          fit_abnormal_rows=int((va.subset == "abnormal").sum()), test_rows=int(len(te)), pi_file=pi_file,
                          brier_fileprior=brier(y, p_file), brier_site1pct=brier(y, p_site), brier_constant=pi_file * (1 - pi_file),
                          max_prob_site1pct=float(p_site.max()), lr_cap=float(cal.lr_cap))
        # 05가 만든 예측 파일에 행 키(subset·rec·pos)로 열을 붙인다. 다시 돌려도 열이 겹치지 않게 먼저 뺀다
        pred = pd.read_csv(OUT / f"test_predictions_{s}.csv").drop(columns=COLS, errors="ignore")
        add = te[["subset", "rec", "pos"]].assign(**{COLS[0]: p_site, COLS[1]: p_file})
        merged = pred.merge(add, on=["subset", "rec", "pos"], how="left", validate="one_to_one")
        if len(merged) != len(pred) or merged[COLS].isna().any().any():
            raise SystemExit("예측 파일과 확률 행이 맞지 않음")
        merged.to_csv(OUT / f"test_predictions_{s}.csv", index=False)
    (OUT / "tvt_probability.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
