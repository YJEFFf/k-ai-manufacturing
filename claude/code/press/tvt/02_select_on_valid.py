"""2단계: 검증(valid) 구간만으로 후보를 채점해 최종 모델과 가설 판정 기준을 고정한다. 시험 구간은 열지 않는다(보고서 1.7·2.5절).

선택 규칙(실행 전 고정): α 1%에서 검증 실시간 행 F1의 A·B 평균이 주 기준이고, 기록 단위 전용 모델은 기록 단위 트랙에서 따로 고른다.
최고값과 0.002 이내면 복잡도(성분 수 + 규칙 수)가 낮은 쪽, 그다음 이름순. 가설 H1(R1)·H2(R2)·H3·H4의 시험 판정 기준도 여기 적는다.
입력: cache/rows_{A,B}.pkl, outputs/tvt_scores_meta.json (01_scores.py 출력)
출력: outputs/tvt_valid.csv, tvt_valid_errors.json, tvt_selection.json, tvt_selection.sha256 (3단계는 이 해시가 맞을 때만 돈다)
실행: python code/press/tvt/02_select_on_valid.py
"""
import json

import pandas as pd

from evalcore import candidates, evaluate, v2_error_anatomy
from lib import ALPHAS, CACHE, OUT, PRIMARY_ALPHA, SPLITS, sha256_file

TIE = 0.002  # 이 차이 안의 후보는 동률로 본다


def main():
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    tables = {s: pd.read_pickle(CACHE / f"rows_{s}.pkl") for s in SPLITS}
    cands = candidates(meta["A"]["complexity"])
    rows = []
    for s, t in tables.items():
        for c in cands:
            for a in ALPHAS:
                for mode, m in evaluate(t, c, a, "valid", meta[s]["r2_ref"]).items():
                    rows.append(dict(split=s, alpha=a, model=c[0], mode=mode, complexity=c[5], **m))
    valid = pd.DataFrame(rows)
    valid.to_csv(OUT / "tvt_valid.csv", index=False)
    errors = {s: v2_error_anatomy(t, PRIMARY_ALPHA, "valid", meta[s]["r2_ref"]) for s, t in tables.items()}
    (OUT / "tvt_valid_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    prim = valid[valid.alpha == PRIMARY_ALPHA]

    def pick(mode):
        """A·B 평균 F1 최고값에서 TIE 안의 후보 중 복잡도가 가장 낮은 것(같으면 이름순)."""
        g = prim[prim["mode"] == mode].groupby("model").agg(f1=("f1", "mean"), complexity=("complexity", "first")).reset_index()
        tied = g[g.f1 >= g.f1.max() - TIE].sort_values(["complexity", "model"])
        return dict(model=tied.iloc[0].model, valid_f1_mean=float(tied.iloc[0].f1), complexity=int(tied.iloc[0].complexity),
                    tied_within_tolerance=tied.model.tolist())

    def vrow(model, mode="realtime"):
        """가설의 검증 근거로 남길 분할별 TP·FP·FN·F1."""
        v = prim[(prim.model == model) & (prim["mode"] == mode)].set_index("split")
        return {s: dict(tp=int(v.loc[s, "tp"]), fp=int(v.loc[s, "fp"]), fn=int(v.loc[s, "fn"]), f1=round(float(v.loc[s, "f1"]), 6)) for s in SPLITS}

    # H3은 두 v3 조건부 성분 중 검증 실시간 F1이 높은 쪽 하나만 시험한다
    c_best = max(["v2+C1d1", "v2+C2d1"], key=lambda m: prim[(prim.model == m) & (prim["mode"] == "realtime")].f1.mean())
    hypotheses = {
        "H1": dict(statement="고장 상태는 수집 공백(수 초)을 넘어 이어진다. 직전 기록이 확인된 이상이면 새 기록 첫 행부터 경보를 유지하면(사건 지속) 기록 시작 직후 미탐이 준다",
                   valid_evidence=dict(v2=vrow("v2"), v2_H1=vrow("v2+H1"),
                                       v2_missed_by_position={s: errors[s]["missed_by_position"] for s in SPLITS}),
                   test_criterion="A·B 모두 시험 미탐 행(v2+H1) < 미탐 행(v2) 이고 시험 오경보 행(v2+H1) ≤ 오경보 행(v2)"),
        "H2": dict(statement="고부하 정상에서 진동 크기 성분만 문턱을 넘을 때 전류 파형은 정상이다. 크기 단독 + 파형 정상인 경보를 보류하면(교차 확인) 탐지를 잃지 않고 오경보가 준다",
                   valid_evidence=dict(v2=vrow("v2"), v2_H2=vrow("v2+H2"),
                                       v2_false_alarms={s: errors[s]["false_alarms"] for s in SPLITS}),
                   test_criterion="A·B 모두 시험 오경보 행(v2+H2) ≤ 오경보 행(v2) 이고 시험 TP(v2+H2) = TP(v2)"),
        "H3": dict(statement="전류 크기(부하)에 따라 진동 정상 범위를 바꾸는 예준 v3 조건부 성분을 v2에 더하면 성능이 오른다",
                   chosen_component=c_best,
                   valid_evidence=dict(v2=vrow("v2"), v2_C=vrow(c_best)),
                   test_criterion=f"시험 실시간 F1 A·B 평균: {c_best} > v2"),
        "H4": dict(statement="정상·이상 파일의 저장 형식 차이(진동 소수 자릿수)만으로 이상을 가를 수 있다(형식 누수). 그래서 정밀도 맞춤(matched)이 필요하다",
                   valid_evidence="형식 규칙은 학습이 필요 없다. 검증 근거 없이 시험에서 바로 판정한다",
                   test_criterion="시험 행에서 '진동 AI0 소수 자릿수 > 6이면 이상' 규칙의 F1 ≥ 0.9"),
    }
    selection = dict(
        protocol=dict(splits={"A": "정상 학습 0~359 / 검증 360~479 / 시험 480~599", "B": "정상 학습 0~299 / 검증 300~419 / 시험 420~599",
                              "abnormal": "이상 21기록 중 앞 10기록 검증, 뒤 11기록 시험, 학습 미사용"},
                      primary_alpha=PRIMARY_ALPHA, tie_tolerance=TIE,
                      rule_constants=dict(incident_gap_s=60, confirm_rows=2, r2_quantile=0.005, r2_min_len=8,
                                          source="60초·2행은 예준 v2 사건·2단계 규칙 값, R² 기준은 정상 학습 자료")),
        selected_realtime=pick("realtime"), selected_record=pick("record"),
        hypotheses=hypotheses,
        # 입력 해시까지 적어 두면 3단계에서 점수 캐시가 바뀌었는지도 확인할 수 있다
        inputs=dict(valid_csv_sha256=sha256_file(OUT / "tvt_valid.csv"), scores_meta_sha256=sha256_file(OUT / "tvt_scores_meta.json"),
                    rows_sha256={s: sha256_file(CACHE / f"rows_{s}.pkl") for s in SPLITS}),
    )
    path = OUT / "tvt_selection.json"
    path.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    # 해시 잠금: 선택 파일을 나중에 고치면 3단계가 멈춘다
    (OUT / "tvt_selection.sha256").write_text(sha256_file(path), encoding="utf-8")

    pd.set_option("display.width", 200)
    for mode in ("realtime", "record"):
        g = prim[prim["mode"] == mode].pivot_table(index="model", columns="split", values="f1").assign(mean=lambda d: d.mean(axis=1))
        print(f"\n== 검증 {mode} F1 (α 1%)\n", g.sort_values("mean", ascending=False).round(4).to_string())
    print("\n선택(실시간):", selection["selected_realtime"])
    print("선택(기록 단위):", selection["selected_record"])
    print("v2 검증 오류:", json.dumps({s: {k: errors[s][k] for k in ("missed_rows", "missed_by_position", "false_alarm_rows")} for s in SPLITS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
