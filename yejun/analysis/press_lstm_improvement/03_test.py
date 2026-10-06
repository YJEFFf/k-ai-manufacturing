"""3단계: 잠긴 선택(outputs/02_selection.json)의 해시가 맞을 때만 test를 채점한다(PROTOCOL.md 6절).

주 비교에 쓰는 LSTM 값은 '새 시드 앙상블(e345)'이다. 잠근 설정을 시드 3·4·5로 다시 학습한 것이라 선택 낙관이 없다.
선택에 쓴 시드 앙상블(e012)과 단일 시드(s0~s5)도 함께 적는다. 모든 변형의 test는 사후 자료로 공개한다.
기준 모델(v2, v2+R1, v2+R1+R2, lstm20 등)은 같은 행 표에서 다시 채점한다(준용 결과와 같음을 00에서 확인).
R1 행은 준용 07과 같이 '이상 흐름을 test 기록부터 따로 돌린 값'(test_only)도 낸다.
출력: outputs/03_test.csv(전 변형), 03_test_refs.csv(기준 모델), 03_comparison.json(주 비교)
실행: PYTHONDONTWRITEBYTECODE=1 python 03_test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402
import lx_scoring as X  # noqa: E402

REFS = ["v2", "v2+H1", "v2+H1+H2", "v1", "lstm20", "lstm20+H1", "mlp_ae5", "mlp_ae5+H1", "maxz3", "knn5", "iforest"]
START = ("W20-none-64x32-e300p30", "raw-last")


def check_lock() -> dict:
    path, lk = H.OUT / "02_selection.json", H.OUT / "02_selection.sha256"
    if not path.exists() or not lk.exists() or H.sha256_file(path) != lk.read_text(encoding="utf-8").strip():
        raise SystemExit("02_selection.json 잠금이 맞지 않는다")
    return json.loads(path.read_text(encoding="utf-8"))


def s07():
    """준용 07_r1_on_baselines.test_only(이상 흐름을 test 기록부터)를 그대로 쓴다."""
    H.tvt()
    spec = importlib.util.spec_from_file_location("tvt_s07", H.TVT / "07_r1_on_baselines.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    t0 = time.time()
    sel = check_lock()
    _, ev, _ = H.tvt()
    m07 = s07()
    rows, refs, infos = [], [], []
    focus = {(sel["track_L"]["cfg"], sel["track_L"]["scoring"]), START,
             (sel["exploratory_LR1"]["cfg"], sel["exploratory_LR1"]["scoring"])}
    for sid in H.SPLITS:
        t, meta, info = X.build_variant_table(sid, ens_sets=("e012", "e345"))
        r2 = meta["r2_ref"]
        infos.append(info)
        for v in info.itertuples():
            ens = v.seed.startswith("e")
            key = (v.cfg, v.scoring)
            for h1 in (False, True):
                # valid는 02에 없는 새 시드(e345, s3~s5)만 여기서 채점한다. 나머지 valid는 02_valid.csv를 쓴다
                fresh = v.seed == "e345" or (not ens and int(v.seed) >= 3)
                for a in (H.ALPHAS if ens else (H.PRIMARY_ALPHA,)):
                    for regime in (("valid", "test") if fresh else ("test",)):
                        for mode, m in H.evaluate(t, v.variant, h1, a, regime, r2).items():
                            rows.append(dict(split=sid, variant=v.variant, rule="R1" if h1 else "none", alpha=a, regime=regime, mode=mode, **m))
                if h1 and (ens or key in focus):
                    to = m07.test_only(t, v.variant, True, False, r2)
                    rows.append(dict(split=sid, variant=v.variant, rule="R1", alpha=H.PRIMARY_ALPHA, regime="test", mode="test_only", **to))
        known = {c[0]: c for c in ev.candidates(meta["complexity"])}
        for name in REFS:
            base = name.split("+")[0]
            c = known.get(name) or (name, base, "+H1" in name, "+H2" in name, False, 1)
            for a in H.ALPHAS:
                for regime in ("valid", "test"):
                    for mode, m in ev.evaluate(t, c, a, regime, r2).items():
                        refs.append(dict(split=sid, model=name, alpha=a, regime=regime, mode=mode, **m))
            if c[2]:
                to = m07.test_only(t, base, True, c[3], r2)
                refs.append(dict(split=sid, model=name, alpha=H.PRIMARY_ALPHA, regime="test", mode="test_only", **to))
        print(sid, "채점 완료", f"{time.time() - t0:.0f}s", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(H.OUT / "03_test.csv", index=False)
    refs = pd.DataFrame(refs)
    refs.to_csv(H.OUT / "03_test_refs.csv", index=False)
    info = pd.concat(infos, ignore_index=True).drop_duplicates("variant")
    valid02 = pd.read_csv(H.OUT / "02_valid.csv").assign(regime="valid")
    allv = pd.concat([res, valid02[~valid02.variant.isin(res[res.regime == "valid"].variant.unique())]], ignore_index=True)

    def row_of(df, name_col, name, rule=None):
        """α 1%에서 분할별 valid·test 실시간 F1, test 미탐·오경보 행, 기록 판정 F1, test_only."""
        d = {name_col: name}
        q = df[(df[name_col] == name) & (df.alpha == H.PRIMARY_ALPHA)]
        if rule is not None:
            q = q[q.rule == rule]
        for sid in H.SPLITS:
            g = lambda regime, mode: q[(q.split == sid) & (q.regime == regime) & (q["mode"] == mode)]  # noqa: E731
            if len(g("valid", "realtime")):
                d[f"valid_{sid}"] = round(float(g("valid", "realtime").f1.iloc[0]), 6)
            tv = g("test", "realtime")
            if len(tv):
                tv = tv.iloc[0]
                d.update({f"test_{sid}": round(float(tv.f1), 6), f"test_fn_{sid}": int(tv.fn), f"test_fp_{sid}": int(tv.fp)})
            if len(g("test", "record")):
                d[f"test_record_{sid}"] = round(float(g("test", "record").f1.iloc[0]), 6)
            if len(g("test", "test_only")):
                d[f"test_only_{sid}"] = round(float(g("test", "test_only").f1.iloc[0]), 6)
        for k in ("valid", "test"):
            if f"{k}_A" in d and f"{k}_B" in d:
                d[f"{k}_mean"] = round((d[f"{k}_A"] + d[f"{k}_B"]) / 2, 6)
        return d

    def family(cfg, scoring, rule):
        names = [X.vname(cfg, scoring, s) for s in ("e345", "e012")] + [X.vname(cfg, scoring, k) for k in range(6)]
        return [row_of(allv, "variant", n, rule) for n in names if (allv.variant == n).any()]

    L, E = sel["track_L"], sel["exploratory_LR1"]
    comp = dict(
        selection=dict(track_L={k: L[k] for k in ("cfg", "scoring", "metric", "dist")},
                       exploratory_LR1={k: E[k] for k in ("cfg", "scoring", "metric", "dist")}),
        track_L=family(L["cfg"], L["scoring"], "none"),
        track_LR1=family(L["cfg"], L["scoring"], "R1"),
        exploratory_LR1=family(E["cfg"], E["scoring"], "R1"),
        start_point=family(START[0], START[1], "none") + family(START[0], START[1], "R1"),
        refs=[row_of(refs, "model", n) for n in REFS],
    )
    # 사후 낙관 상한: e012 앙상블 중 test 실시간 F1(A·B 평균)이 가장 높은 변형(규칙별)
    p = res[(res.alpha == H.PRIMARY_ALPHA) & (res["mode"] == "realtime") & (res.regime == "test") & res.variant.str.endswith(":e012")]
    post = p.groupby(["variant", "rule"]).f1.mean().reset_index()
    comp["post_hoc_best_test_e012"] = {r: post[post.rule == r].nlargest(5, "f1").round(4).to_dict("records") for r in ("none", "R1")}
    comp["seconds"] = round(time.time() - t0, 1)
    H.dump(comp, H.OUT / "03_comparison.json")
    if H.sha256_file(H.OUT / "02_selection.json") != (H.OUT / "02_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("채점 중 선택 파일이 바뀌었다")
    pd.set_option("display.width", 250)
    for k in ("track_L", "track_LR1", "exploratory_LR1", "start_point", "refs"):
        print(f"\n== {k}")
        print(pd.DataFrame(comp[k]).to_string(index=False))
    print(json.dumps(comp["post_hoc_best_test_e012"], ensure_ascii=False, indent=1))
    print(f"{comp['seconds']}s")


if __name__ == "__main__":
    main()
