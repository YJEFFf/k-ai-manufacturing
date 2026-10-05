"""3단계: 고정된 선택(tvt_selection.json)의 해시가 맞을 때만 시험(test) 구간을 한 번 채점한다(보고서 2.4·2.5·3.4절).

모든 후보의 시험 점수를 공개하고 선택 모델을 표시한다. 가설 H1(R1)~H4를 2단계에 적어 둔 기준으로 판정한다.
채점 전후로 선택 파일 해시를 확인해, 시험 결과를 본 뒤 선택을 고치지 않았음을 남긴다.
입력: cache/rows_{A,B}.pkl, outputs/tvt_selection.json(.sha256), tvt_scores_meta.json, 팀 레포 원자료(H4 형식 누수용)
출력: outputs/tvt_test.csv, tvt_hypotheses.json, tvt_summary.md
실행: python code/press/tvt/03_score_test.py --repo <팀 레포>
"""
import json

import numpy as np
import pandas as pd

from evalcore import candidates, evaluate, v2_error_anatomy
from lib import ALPHAS, CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, repo_arg, sha256_file


def check_selection():
    """선택 파일과 점수 캐시가 2단계 때와 같은지 해시로 확인하고 선택 내용을 돌려준다."""
    path, lock = OUT / "tvt_selection.json", OUT / "tvt_selection.sha256"
    if not path.exists() or not lock.exists():
        raise SystemExit("2단계 선택 파일이 없다. 02_select_on_valid.py를 먼저 실행한다")
    if sha256_file(path) != lock.read_text(encoding="utf-8").strip():
        raise SystemExit("선택 파일이 2단계 이후 바뀌었다")
    sel = json.loads(path.read_text(encoding="utf-8"))
    for s in SPLITS:
        if sha256_file(CACHE / f"rows_{s}.pkl") != sel["inputs"]["rows_sha256"][s]:
            raise SystemExit("점수 캐시가 2단계 이후 바뀌었다")
    return sel


def format_leak(repo, tables):
    """시험 행에서 '진동 AI0 소수 자릿수 > 6이면 이상' 규칙(학습 없음)의 F1."""
    d = repo / "yejun/press_submission/data/3_소성가공_예지보전"
    # 자릿수를 보려면 원자료를 문자열로 읽어야 한다
    raw = pd.concat([pd.read_csv(d / f, dtype={"AI0_Vibration": str}) for f in ("press_data_normal.csv", "outlier_data.csv")])
    digits = raw.AI0_Vibration.str.split(".").str[1].fillna("").str.len()
    # 행 표와 나노초 시각으로 맞춘다. 같은 시각 중복 행은 첫 행만 쓴다
    key = pd.Series((digits > 6).to_numpy(), index=pd.to_datetime(raw.TimeStamp).astype("datetime64[ns]").astype("int64").to_numpy())
    key = key[~key.index.duplicated()]
    out = {}
    for s, t in tables.items():
        m = t.part == "test"
        pred = t.loc[m, "ts"].astype("int64").map(key).to_numpy().astype(bool)
        out[s] = f1_counts(t.loc[m, "label"].to_numpy() == 1, pred)
    return out


def main():
    repo = repo_arg()
    sel = check_selection()
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    tables = {s: pd.read_pickle(CACHE / f"rows_{s}.pkl") for s in SPLITS}
    cands = candidates(meta["A"]["complexity"])
    rows = []
    for s, t in tables.items():
        for c in cands:
            for a in ALPHAS:
                for mode, m in evaluate(t, c, a, "test", meta[s]["r2_ref"]).items():
                    rows.append(dict(split=s, alpha=a, model=c[0], mode=mode, complexity=c[5], **m))
    test = pd.DataFrame(rows)
    test["selected"] = ((test["mode"] == "realtime") & (test.model == sel["selected_realtime"]["model"])) | \
                       ((test["mode"] == "record") & (test.model == sel["selected_record"]["model"]))
    test.to_csv(OUT / "tvt_test.csv", index=False)
    prim = test[test.alpha == PRIMARY_ALPHA]

    def row(model, s, mode="realtime"):
        """α 1% 시험 결과 한 줄."""
        return prim[(prim.model == model) & (prim.split == s) & (prim["mode"] == mode)].iloc[0]

    # 가설 판정: 2단계 test_criterion 문장을 그대로 코드로 옮긴 것
    h = sel["hypotheses"]
    verdict = {}
    verdict["H1"] = all(row("v2+H1", s).fn < row("v2", s).fn and row("v2+H1", s).fp <= row("v2", s).fp for s in SPLITS)
    verdict["H2"] = all(row("v2+H2", s).fp <= row("v2", s).fp and row("v2+H2", s).tp == row("v2", s).tp for s in SPLITS)
    c = h["H3"]["chosen_component"]
    verdict["H3"] = float(np.mean([row(c, s).f1 for s in SPLITS])) > float(np.mean([row("v2", s).f1 for s in SPLITS]))
    leak = format_leak(repo, tables)
    verdict["H4"] = all(v["f1"] >= 0.9 for v in leak.values())
    detail = {k: dict(statement=h[k]["statement"], test_criterion=h[k]["test_criterion"], supported=bool(v)) for k, v in verdict.items()}
    detail["H1"]["test"] = {s: {m: dict(fn=int(row(m, s).fn), fp=int(row(m, s).fp)) for m in ("v2", "v2+H1")} for s in SPLITS}
    detail["H2"]["test"] = {s: {m: dict(tp=int(row(m, s).tp), fp=int(row(m, s).fp)) for m in ("v2", "v2+H2")} for s in SPLITS}
    detail["H3"]["test"] = {s: {m: round(float(row(m, s).f1), 6) for m in ("v2", c)} for s in SPLITS}
    detail["H4"]["test"] = leak
    errors = {s: v2_error_anatomy(t, PRIMARY_ALPHA, "test", meta[s]["r2_ref"]) for s, t in tables.items()}
    (OUT / "tvt_hypotheses.json").write_text(json.dumps(dict(hypotheses=detail, v2_test_errors=errors), ensure_ascii=False, indent=2), encoding="utf-8")

    # 요약
    lines = ["# train/valid/test 결과 (α 1%)", ""]
    for mode, key in (("realtime", "selected_realtime"), ("record", "selected_record")):
        m = sel[key]["model"]
        lines.append(f"- 선택({mode}): **{m}** — 검증 F1 평균 {sel[key]['valid_f1_mean']:.4f} → 시험 F1 A {row(m, 'A', mode).f1:.4f} · B {row(m, 'B', mode).f1:.4f}")
    lines += ["", "## 시험 F1 (전 후보)", ""]
    for mode in ("realtime", "record"):
        g = prim[prim["mode"] == mode].pivot_table(index="model", columns="split", values="f1").assign(mean=lambda d: d.mean(axis=1))
        lines += [f"### {mode}", "", "```", g.sort_values("mean", ascending=False).round(4).to_string(), "```", ""]
    lines += ["## 가설 판정", ""] + [f"- {k}: {'채택' if v else '기각'} — {h[k]['test_criterion']}" for k, v in verdict.items()]
    (OUT / "tvt_summary.md").write_text("\n".join(lines), encoding="utf-8")

    # 채점 뒤 한 번 더: 채점하는 동안 선택 파일이 바뀌지 않았는지
    if sha256_file(OUT / "tvt_selection.json") != (OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("채점 중 선택 파일이 바뀌었다")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
