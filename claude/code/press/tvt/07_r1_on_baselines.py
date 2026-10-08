"""7단계(사후, test 채점 이후): R1(사건 지속)을 기준선에도 붙여 본다. 선택·잠금·최종 선정에는 쓰지 않는다.

R1은 기반 모델과 상관없이 붙일 수 있는 규칙이라 기준선에 붙였을 때 test 성적이 어떻게 되는지 보고서 2.4절에 공개한다.
- 흐름 이어감: 02·03과 같은 방식(이상 21기록을 시간순으로 이어 돌리고 test 행만 채점)
- test만 따로: 이상 흐름을 test 기록부터 시작(직전 valid 기록의 경보 상태 없이). 사건 첫 기록을 늦게 잡는 모델의 약점이 드러난다
- 점수 없음: 창이 아직 차지 않아 점수가 없는 test 이상 행(LSTM 20행 창, MLP 5행 창)
출력: outputs/tvt_r1_baselines.csv, outputs/tvt_unscored.csv
실행: python code/press/tvt/07_r1_on_baselines.py
"""
import json
import math

import numpy as np
import pandas as pd

from evalcore import candidates, evaluate, own_alarm
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, sha256_file, stream_rules

BASES = ["iforest", "lstm20", "mlp_ae5", "maxz3", "knn5", "v1", "v2"]


def test_only(t, base, h1, h2, r2_ref):
    """이상 흐름을 test 기록부터 시작해 채점한다(정상 흐름은 02·03과 같이 valid → test)."""
    ys, ps = [], []
    for subset, parts in (("normal", ("valid", "test")), ("abnormal", ("test",))):
        stream = ((t.subset == subset) & t.part.isin(parts)).to_numpy()
        sub = t.loc[stream]
        own = own_alarm(t, stream, base, PRIMARY_ALPHA, "test", h2, r2_ref)
        rt, _ = stream_rules(sub.ts.to_numpy(), sub.rec.to_numpy(), own, sub.prefix_r2.to_numpy() >= r2_ref, h1)
        keep = (sub.part == "test").to_numpy()
        ys.append(sub.label.to_numpy()[keep] == 1); ps.append(np.asarray(rt)[keep].astype(bool))
    return f1_counts(np.concatenate(ys), np.concatenate(ps))


def main():
    # 05·06과 같은 확인: 잠긴 선택 파일과 점수 캐시가 그대로일 때만 돈다
    sel = json.loads((OUT / "tvt_selection.json").read_text(encoding="utf-8"))
    if sha256_file(OUT / "tvt_selection.json") != (OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("선택 파일 해시 불일치")
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    cx = meta["A"]["complexity"]
    known = {c[0]: c for c in candidates(cx)}
    table = pd.read_csv(OUT / "tvt_test.csv").query("mode == 'realtime' and alpha == @PRIMARY_ALPHA")
    rows, unscored = [], []
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        if sha256_file(CACHE / f"rows_{s}.pkl") != sel["inputs"]["rows_sha256"][s]:
            raise SystemExit("점수 캐시 해시 불일치")
        r2 = meta[s]["r2_ref"]
        for base in BASES:
            for h1, h2 in ((False, False), (True, False)) + (((True, True),) if base == "v2" else ()):
                name = base + ("+H1" if h1 else "") + ("+H2" if h2 else "")
                cand = known.get(name, (name, base, h1, h2, False, cx[base] + h1 + h2))   # 기준선+R1은 잠금 후보에 없던 조합
                te = evaluate(t, cand, PRIMARY_ALPHA, "test", r2)["realtime"]
                va = evaluate(t, cand, PRIMARY_ALPHA, "valid", r2)["realtime"]
                if name in known:   # 잠금 후보였던 조합은 03의 표와 같아야 같은 계산이다
                    ref = table.query("split == @s and model == @name").f1
                    if len(ref) != 1 or not math.isclose(te["f1"], float(ref.iloc[0]), abs_tol=1e-9):
                        raise SystemExit(f"test F1이 tvt_test.csv와 다름: {s} {name}")
                to = test_only(t, base, h1, h2, r2)
                rows.append(dict(split=s, model=name, in_lock_candidates=name in known, valid_f1=va["f1"], test_f1=te["f1"],
                                 test_tp=te["tp"], test_fp=te["fp"], test_fn=te["fn"], test_only_f1=to["f1"]))
        m = ((t.subset == "abnormal") & (t.part == "test")).to_numpy()
        for base in ("lstm20", "mlp_ae5", "v2"):
            p = t.loc[m, f"{base}|p_full"].to_numpy()
            unscored.append(dict(split=s, model=base, test_abnormal_rows=int(m.sum()), no_score_rows=int((~np.isfinite(p)).sum())))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "tvt_r1_baselines.csv", index=False)
    pd.DataFrame(unscored).to_csv(OUT / "tvt_unscored.csv", index=False)
    print(out.round(4).to_string(index=False))
    print(pd.DataFrame(unscored).to_string(index=False))


if __name__ == "__main__":
    main()
