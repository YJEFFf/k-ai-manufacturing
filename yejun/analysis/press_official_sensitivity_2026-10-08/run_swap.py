"""3단계: 잠금 선택 규칙 교차 확인 — 이상 기록 역할 앞뒤 바꾸기(뒤 11기록 = valid, 앞 10기록 = test).

공식 02_select_on_valid.main을 고치지 않고 CACHE·OUT만 임시 폴더로 돌려 실행한다(같은 후보·복잡도·α 1%·동률 폭 0.002).
대조: 바꾸지 않은 표로 같은 실행을 해 공식 tvt_valid.csv·선택이 그대로 나오는지 먼저 확인한다.
test(앞 10기록)는 evalcore.evaluate(..., "test")로 모든 후보·α를 채점한다. 앞 10기록이 시간상 먼저라 valid 쪽 경보 상태는 test로 이어지지 않는다.
같은 단일 사건의 앞뒤를 바꾼 것이라 독립 반복이 아니다. 결과가 무엇이든 공식 모델을 바꾸지 않는다.
출력: outputs/swap_valid.csv, swap_selection.json, swap_test.csv, swap_valid_ranking_alpha01.csv, swap_summary.json
실행: PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python run_swap.py
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil

import numpy as np
import pandas as pd

import sens_common as C

OUT = C.OUT
SWAP_WORK = C.WORK / "swap_runs"
N_FRONT = 10   # lib.ABN_VALID_RECORDS


def swap_roles(t: pd.DataFrame) -> pd.DataFrame:
    """이상 행의 part만 바꾼다: 기록 0~9 → test, 10~20 → valid. rec 이름도 새 역할로 맞춘다. 점수·p값은 그대로."""
    t = t.copy()
    ab = (t["subset"] == "abnormal").to_numpy()
    seg = t["seg"].to_numpy()
    part = t["part"].to_numpy(dtype=object).copy()
    part[ab] = np.where(seg[ab] < N_FRONT, "test", "valid")
    rec = t["rec"].to_numpy(dtype=object).copy()
    rec[ab] = [f"{p}:abnormal:{s}" for p, s in zip(part[ab], seg[ab])]
    t["part"] = pd.Series(part, index=t.index).astype(t["part"].dtype)
    t["rec"] = pd.Series(rec, index=t.index).astype(t["rec"].dtype)
    return t


def run_official_selection(tag: str, tables: dict | None):
    """02_select_on_valid.main을 임시 CACHE·OUT으로 실행. tables=None이면 공식 캐시 파일을 그대로 복사해 쓴다."""
    root = SWAP_WORK / tag
    if root.exists():
        shutil.rmtree(root)
    cache, out = root / "cache", root / "outputs"
    cache.mkdir(parents=True)
    out.mkdir(parents=True)
    for s in C.SPLITS:
        if tables is None:
            shutil.copy2(C.TVT / "cache" / f"rows_{s}.pkl", cache / f"rows_{s}.pkl")
        else:
            tables[s].to_pickle(cache / f"rows_{s}.pkl")
    shutil.copy2(C.TVT / "outputs" / "tvt_scores_meta.json", out / "tvt_scores_meta.json")
    S02 = C.load_module(f"tvt_s02_{tag}", "02_select_on_valid.py")
    S02.CACHE, S02.OUT = cache, out          # main()이 호출 때 읽는 모듈 전역
    assert S02.TIE == 0.002 and S02.PRIMARY_ALPHA == C.PRIMARY_ALPHA
    assert (C.lib.GAP_S, C.lib.CONFIRM_ROWS, C.lib.R2_MIN_LEN) == (60.0, 2, 8)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        S02.main()
    (root / "stdout.txt").write_text(buf.getvalue(), encoding="utf-8")
    sel = json.loads((out / "tvt_selection.json").read_text(encoding="utf-8"))
    return sel, out


def score_all(tables, meta, cands, sel):
    """03_score_test.py와 같은 채점(모든 후보 × α), 선택 표시."""
    rows = []
    for s, t in tables.items():
        for c in cands.values():
            for a in C.ALPHAS:
                for mode, m in C.evalcore.evaluate(t, c, a, "test", meta[s]["r2_ref"]).items():
                    rows.append(dict(split=s, alpha=a, model=c[0], mode=mode, complexity=c[5], **m))
    test = pd.DataFrame(rows)
    test["selected"] = ((test["mode"] == "realtime") & (test.model == sel["selected_realtime"]["model"])) | \
                       ((test["mode"] == "record") & (test.model == sel["selected_record"]["model"]))
    return test


def pick(df, s, model, mode="realtime", alpha=0.01):
    r = df[(df.split == s) & (df.model == model) & (df["mode"] == mode) & np.isclose(df.alpha, alpha)]
    assert len(r) == 1, (s, model, mode, alpha)
    r = r.iloc[0]
    return dict(tp=int(r.tp), fp=int(r.fp), fn=int(r.fn), f1=float(r.f1))


def main():
    tables, meta = C.load_tables(), C.load_meta()
    cands = C.candidates_by_name(meta)
    official_dir = C.TVT / "outputs"

    # ---- 대조: 바꾸지 않은 표 → 공식 산출물과 같아야 한다
    sel0, out0 = run_official_selection("control_unswapped", None)
    ctrl = dict(
        valid_csv_identical_bytes=C.sha256_file(out0 / "tvt_valid.csv") == C.sha256_file(official_dir / "tvt_valid.csv"),
        valid_csv_identical_lf=C.sha256_lf(out0 / "tvt_valid.csv") == C.sha256_lf(official_dir / "tvt_valid.csv"),
        valid_csv_identical_to_claude_repo_lf=C.sha256_lf(out0 / "tvt_valid.csv") == C.sha256_lf(C.CLAUDE_TVT / "outputs" / "tvt_valid.csv"),
        selection_json_identical_bytes=C.sha256_file(out0 / "tvt_selection.json") == C.sha256_file(official_dir / "tvt_selection.json"),
        selected_realtime=sel0["selected_realtime"], selected_record=sel0["selected_record"],
    )
    off_sel = json.loads((official_dir / "tvt_selection.json").read_text(encoding="utf-8"))
    ctrl["same_selection_as_official"] = (sel0["selected_realtime"] == off_sel["selected_realtime"]
                                          and sel0["selected_record"] == off_sel["selected_record"])
    if not (ctrl["valid_csv_identical_lf"] and ctrl["same_selection_as_official"]):
        C.dump(ctrl, OUT / "swap_summary.json")
        raise SystemExit("대조 실행이 공식 선택을 재현하지 못했다")
    print("대조(바꾸지 않음) 재현:", ctrl["valid_csv_identical_bytes"], ctrl["same_selection_as_official"], sel0["selected_realtime"]["model"])

    # ---- 앞뒤 바꾸기
    sw = {s: swap_roles(t) for s, t in tables.items()}
    for s, t in sw.items():
        ab = t[t.subset == "abnormal"]
        assert sorted(ab[ab.part == "test"].seg.unique()) == list(range(N_FRONT))
        assert sorted(ab[ab.part == "valid"].seg.unique()) == list(range(N_FRONT, 21))
        # 점수·p값·정상 행은 그대로
        same_cols = [c for c in t.columns if c not in ("part", "rec")]
        assert t[same_cols].equals(tables[s][same_cols])
        assert (t.loc[t.subset == "normal", ["part", "rec"]].to_numpy() == tables[s].loc[tables[s].subset == "normal", ["part", "rec"]].to_numpy()).all()
    sel1, out1 = run_official_selection("swapped", sw)
    shutil.copy2(out1 / "tvt_valid.csv", OUT / "swap_valid.csv")
    shutil.copy2(out1 / "tvt_selection.json", OUT / "swap_selection.json")
    test = score_all(sw, meta, cands, sel1)
    test.to_csv(OUT / "swap_test.csv", index=False)

    valid = pd.read_csv(out1 / "tvt_valid.csv")
    prim = valid[np.isclose(valid.alpha, C.PRIMARY_ALPHA)]
    rank = []
    for mode in ("realtime", "record"):
        g = prim[prim["mode"] == mode].pivot_table(index="model", columns="split", values="f1").assign(mean=lambda d: d.mean(axis=1))
        g["complexity"] = prim[prim["mode"] == mode].groupby("model").complexity.first()
        g["mode"] = mode
        rank.append(g.sort_values("mean", ascending=False).reset_index())
    rank = pd.concat(rank, ignore_index=True)
    rank.to_csv(OUT / "swap_valid_ranking_alpha01.csv", index=False)

    off_test = pd.read_csv(official_dir / "tvt_test.csv")
    off_valid = pd.read_csv(official_dir / "tvt_valid.csv")
    chosen = sel1["selected_realtime"]["model"]
    models = list(dict.fromkeys([chosen, "v2+H1", "v2+H1+H2", "v2"]))
    summary = dict(
        caveat="같은 단일 고장 사건(이상 21기록)의 앞뒤 역할만 바꾼 것. 독립 반복이 아니며 공식 모델·상수를 바꾸지 않는다.",
        roles=dict(valid_abnormal="기록 10~20 (11기록, 324행)", test_abnormal="기록 0~9 (10기록, 276행)", normal="공식 분할 그대로"),
        control_unswapped=ctrl,
        swapped_selection=dict(selected_realtime=sel1["selected_realtime"], selected_record=sel1["selected_record"]),
        swapped_valid_back11_alpha01={m: {s: pick(valid, s, m) for s in C.SPLITS} for m in models},
        swapped_test_front10_alpha01={m: {s: pick(test, s, m) for s in C.SPLITS} for m in models},
        swapped_test_front10_record_selected={sel1["selected_record"]["model"]: {s: pick(test, s, sel1["selected_record"]["model"], "record") for s in C.SPLITS}},
        swapped_test_front10_other_alphas={str(a): {m: {s: pick(test, s, m, alpha=a)["f1"] for s in C.SPLITS} for m in ("v2+H1", "v2+H1+H2", "v2")}
                                           for a in C.ALPHAS if a != C.PRIMARY_ALPHA},
        official_for_comparison=dict(
            selected_realtime=off_sel["selected_realtime"], selected_record=off_sel["selected_record"],
            test_back11_alpha01={m: {s: pick(off_test, s, m) for s in C.SPLITS} for m in ("v2+H1", "v2+H1+H2", "v2")},
            valid_front10_alpha01={m: {s: pick(off_valid, s, m) for s in C.SPLITS} for m in ("v2+H1", "v2+H1+H2", "v2")}),
    )
    C.dump(summary, OUT / "swap_summary.json")
    print("바꾼 선택(실시간):", sel1["selected_realtime"])
    print("바꾼 선택(기록):", sel1["selected_record"])
    for m in models:
        print(m, {s: round(summary["swapped_test_front10_alpha01"][m][s]["f1"], 6) for s in C.SPLITS})


if __name__ == "__main__":
    main()
