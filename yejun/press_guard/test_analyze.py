"""analyze.py·verify.py의 계약 검사: 조건표 분모·오류 합, 첫 경보표, 통합 비교표 일관성, verify의 변조 검출."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest

import verify
from model import HERE

OUT = HERE / "outputs"


@pytest.fixture(scope="module")
def tables():
    need = ["metrics.csv", "error_conditions_v2.csv", "records_first_alarm_v2.csv", "model_comparison_v2.csv", "uncertainty_v2.csv", "workload_v2.csv"]
    if not all((OUT / n).is_file() for n in need):
        pytest.skip("analyze.py 결과가 없다")
    return {n: pd.read_csv(OUT / n) for n in need}


def test_error_condition_sums_match_metrics(tables):
    cond, metrics = tables["error_conditions_v2.csv"], tables["metrics.csv"]
    for sid in ("A", "B"):
        m = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
        for condition in ("pos_bin", "len_bin", "vib_quartile", "amp_quartile", "strongest_component"):
            c = cond[cond.split_id.eq(sid) & cond.model.eq("v2") & cond.alpha.eq(.01) & cond.condition.eq(condition)]
            abn, nor = c[c.subset.eq("abnormal")], c[c.subset.eq("normal")]
            assert abn.rows.sum() == 600 and abn.error_rows.sum() == m.fn, (sid, condition)
            if len(nor):
                assert nor.rows.sum() == m.tn + m.fp and nor.error_rows.sum() == m.fp, (sid, condition)


def test_records_first_alarm_consistent(tables):
    r, metrics = tables["records_first_alarm_v2.csv"], tables["metrics.csv"]
    for sid in ("A", "B"):
        x = r[r.split_id.eq(sid)]
        assert len(x) == 21 and x.rows.sum() == 600
        for model, name in (("v1", "baseline_v1"), ("v2", "guard_v2")):
            m = metrics[metrics.split.eq(sid) & metrics.model.eq(name) & metrics.alpha.eq(.01)].iloc[0]
            assert x[f"{model}_fn_rows"].sum() == m.fn
            assert np.nanmax(x[f"{model}_first_alarm_s"]) == pytest.approx(m.delay_max_s)
        assert (x.v2_first_alarm_position <= x.v1_first_alarm_position).all()   # v2는 v1보다 늦게 경보하지 않는다


def test_comparison_contains_v1_and_v2_on_same_protocol(tables):
    c = tables["model_comparison_v2.csv"]
    main = c[c.calibration_unit.eq("recording_segments") & c.criterion.eq("conformal") & c.alpha.eq(.01)]
    assert set(main.model) >= {"combined_w8", "early6_ar2", "lstm20", "isolation_forest", "sine_w8", "maxz_3"}
    assert main.is_final_model.sum() == 2 and main.is_main_model.sum() == 2
    metrics = tables["metrics.csv"]
    for sid in ("A", "B"):
        row = main[main.split_id.eq(sid) & main.model.eq("early6_ar2")].iloc[0]
        m = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
        assert (row.fn, row.fp) == (m.fn, m.fp) and row.f1_all_rows == pytest.approx(m.f1, abs=1e-12)


def test_uncertainty_and_workload_observed_match(tables):
    u, w, metrics = tables["uncertainty_v2.csv"], tables["workload_v2.csv"], tables["metrics.csv"]
    for sid in ("A", "B"):
        for model, name in (("v1", "baseline_v1"), ("v2", "guard_v2")):
            for alpha in (.01, .03, .05):
                m = metrics[metrics.split.eq(sid) & metrics.model.eq(name) & metrics.alpha.eq(alpha)].iloc[0]
                x = u[u.split_id.eq(sid) & u.model.eq(model) & u.alpha.eq(alpha)]
                assert (x[x.statistic.eq("notified_segments")].observed == m.normal_notified_segments).all()
                assert (x[x.statistic.eq("fn_rows")].observed == m.fn).all()
                assert ((x.boot_p2_5 <= x.observed) & (x.observed <= x.boot_p97_5)).all()
                ww = w[w.split_id.eq(sid) & w.model.eq(name) & w.alpha.eq(alpha)].iloc[0]
                assert ww.first_alert_segments == m.normal_notified_segments and ww.scenario_alerts_per_day_8h_recorded_rate == pytest.approx(ww.alerts_per_recorded_hour * 8)
                # α는 구간당 비율: 보정 120구간이 허용하는 명목 비율과 경과시간 환산(루브릭 검수 R8)
                assert ww.alpha_grid_rate == pytest.approx(np.floor(alpha * 121 + 1e-9) / 121)
                assert ww.nominal_alerts_per_8h_elapsed == pytest.approx(ww.alpha_grid_rate * ww.units_per_elapsed_hour * 8)
                assert ww.observed_alerts_per_8h_elapsed == pytest.approx(ww.alerts_per_elapsed_hour * 8)
                assert ww.observed_rate_upper95 >= ww.first_alert_segments / ww.normal_segments


def test_verify_detects_tampering(tmp_path):
    if not (OUT / "expected").is_dir():
        pytest.skip("동결 기대값이 없다")
    out = tmp_path / "outputs"
    shutil.copytree(OUT, out)
    art = tmp_path / "artifacts"; shutil.copytree(HERE / "artifacts", art)
    assert verify.main(["--out", str(out), "--artifacts", str(art)]) == 0
    m = pd.read_csv(out / "uncertainty_v2.csv"); m.loc[0, "boot_mean"] += 1e-6; m.to_csv(out / "uncertainty_v2.csv", index=False)
    assert verify.main(["--out", str(out), "--artifacts", str(art)]) == 1
    shutil.copy2(OUT / "uncertainty_v2.csv", out / "uncertainty_v2.csv")
    assert verify.main(["--out", str(out), "--artifacts", str(art)]) == 0
    a = json.loads((art / "guard_A.json").read_text(encoding="utf-8")); a["state"]["ar2"][0] += 1; (art / "guard_A.json").write_text(json.dumps(a), encoding="utf-8")
    assert verify.main(["--out", str(out), "--artifacts", str(art)]) == 1
    assert verify.main(["--out", str(out), "--artifacts", str(art), "--freeze"]) == 2


def test_verify_compares_row_level_predictions(tmp_path):
    """행 단위 예측 파일 한 행을 바꾸면 verify의 예측 요약 대조가 실패한다(평가관 06 R5). 1e-9 수준의 부동소수 차이는 통과하고,
    점수 한 행을 1.0 바꾸거나 두 행의 점수를 맞바꾸면 실패한다(적대적 검수 C-03: 합·제곱합 요약은 맞바꿈을 놓쳤다)."""
    if not (OUT / "expected" / verify.DIGEST).is_file():
        pytest.skip("동결 예측 요약이 없다")
    out = tmp_path / "outputs"; (out / "expected").mkdir(parents=True)
    shutil.copy2(OUT / "expected" / verify.DIGEST, out / "expected" / verify.DIGEST)
    for name in verify.PREDICTIONS:
        shutil.copy2(OUT / name, out / name)
    assert all(r["ok"] for r in verify.compare_predictions(out, out / "expected"))
    t = pd.read_csv(out / "test_predictions_A.csv")
    t.loc[t.index[t.alarm.eq(0)][0], "alarm"] = 1
    t.to_csv(out / "test_predictions_A.csv", index=False)
    bad = {r["file"]: r["ok"] for r in verify.compare_predictions(out, out / "expected")}
    assert bad["test_predictions_A.csv"] is False and bad["test_predictions_B.csv"] is True
    t = pd.read_csv(OUT / "test_predictions_A.csv")
    t["score"] = t.score + 1e-9                                          # 다른 기기의 부동소수 차이 수준
    t.to_csv(out / "test_predictions_A.csv", index=False)
    ok = {r["file"]: r for r in verify.compare_predictions(out, out / "expected")}
    assert ok["test_predictions_A.csv"]["ok"] and "부동소수 차이" in ok["test_predictions_A.csv"].get("note", "")
    t = pd.read_csv(OUT / "test_predictions_A.csv"); t.loc[5, "score"] += 1.0
    t.to_csv(out / "test_predictions_A.csv", index=False)
    assert not {r["file"]: r["ok"] for r in verify.compare_predictions(out, out / "expected")}["test_predictions_A.csv"]
    t = pd.read_csv(OUT / "test_predictions_A.csv")
    hi, lo = int(t.score.idxmax()), int(t.score.idxmin())
    t.loc[[hi, lo], "score"] = t.loc[[lo, hi], "score"].to_numpy()          # 합·제곱합·최솟값·최댓값은 그대로인 맞바꿈
    t.to_csv(out / "test_predictions_A.csv", index=False)
    r = {r["file"]: r for r in verify.compare_predictions(out, out / "expected")}["test_predictions_A.csv"]
    assert not r["ok"] and "score" in r["reason"]
    t = pd.read_csv(OUT / "test_predictions_A.csv")
    small = t.anomaly_probability < 1e-3
    t.loc[small, "anomaly_probability"] *= 3                                  # 작은 값 열을 몇 배로(코드 검토 R1-05)
    t.to_csv(out / "test_predictions_A.csv", index=False)
    assert not {r["file"]: r["ok"] for r in verify.compare_predictions(out, out / "expected")}["test_predictions_A.csv"]
    t = pd.read_csv(OUT / "test_predictions_A.csv"); t["score"] = t.score + 0.0009                   # 모든 행을 조금씩 옮기기
    t.to_csv(out / "test_predictions_A.csv", index=False)
    assert not {r["file"]: r["ok"] for r in verify.compare_predictions(out, out / "expected")}["test_predictions_A.csv"]
    for shift, passes in ((5e-5, True), (2e-3, False)):         # 순위 구간 최솟값 행의 한 칸 뒤바뀜(검토 3)은 통과, 행별 허용 밖은 실패
        t = pd.read_csv(OUT / "test_predictions_A.csv"); t.loc[t.score.idxmin(), "score"] += shift
        t.to_csv(out / "test_predictions_A.csv", index=False)
        assert {r["file"]: r["ok"] for r in verify.compare_predictions(out, out / "expected")}["test_predictions_A.csv"] is passes


def test_refit_sensitivity_and_ablation_contract(tables):
    """재적합 민감도(3전처리×2모델)와 절제(5후보)가 있고, matched 재적합 v2는 저장 모델 지표와 같다."""
    s = pd.read_csv(OUT / "sensitivity_v2.csv"); a = pd.read_csv(OUT / "ablation_v2.csv"); metrics = tables["metrics.csv"]
    assert set(s.fit_variant) == {"raw", "matched", "coarse"} and set(s.model) == {"v2", "v1_combined_w8"}
    assert set(a.model) == {"v2", "no_magnitude", "no_waveform", "no_dynamics", "no_early_switch"}
    for sid in ("A", "B"):
        m = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
        r = s[s.split_id.eq(sid) & s.fit_variant.eq("matched") & s.model.eq("v2") & s.criterion.eq("conformal") & s.alpha.eq(.01)].iloc[0]
        assert (r.tp, r.fp, r.fn) == (m.tp, m.fp, m.fn)
        v1 = metrics[metrics.split.eq(sid) & metrics.model.eq("baseline_v1") & metrics.alpha.eq(.01)].iloc[0]
        r1 = s[s.split_id.eq(sid) & s.fit_variant.eq("matched") & s.model.eq("v1_combined_w8") & s.criterion.eq("conformal") & s.alpha.eq(.01)].iloc[0]
        assert (r1.tp, r1.fp, r1.fn) == (v1.tp, v1.fp, v1.fn)
        full = a[a.split_id.eq(sid) & a.model.eq("v2") & a.criterion.eq("conformal") & a.alpha.eq(.01)].iloc[0]
        assert (full.tp, full.fp, full.fn) == (m.tp, m.fp, m.fn)


def test_segment_conditions_and_interaction_denominators(tables):
    """구간 단위 조건표의 분모는 이상 21·정상 120/180이고, 오류 구간 합은 지표의 구간 수와 같다. 2×2 셀 합도 같다."""
    c = pd.read_csv(OUT / "error_conditions_segments_v2.csv"); i = pd.read_csv(OUT / "interaction_2x2_v2.csv"); metrics = tables["metrics.csv"]
    for sid, n_normal in (("A", 120), ("B", 180)):
        for model, name in (("v1", "baseline_v1"), ("v2", "guard_v2")):
            m = metrics[metrics.split.eq(sid) & metrics.model.eq(name) & metrics.alpha.eq(.01)].iloc[0]
            for cond in ("len_bin", "vib_quartile", "amp_quartile", "vib_high", "wave"):
                x = c[c.split_id.eq(sid) & c.model.eq(model) & c.alpha.eq(.01) & c.condition.eq(cond)]
                abn, nor = x[x.subset.eq("abnormal")], x[x.subset.eq("normal")]
                assert abn.segments.sum() == 21 and abn.error_segments.sum() == 21 - m.abnormal_notified_segments, (sid, model, cond)
                assert nor.segments.sum() == n_normal and nor.error_segments.sum() == m.normal_notified_segments, (sid, model, cond)
            y = i[i.split_id.eq(sid) & i.model.eq(model) & i.alpha.eq(.01)]
            assert y[y.subset.eq("abnormal")].segments.sum() == 21 and y[y.subset.eq("normal")].segments.sum() == n_normal
            assert y[y.subset.eq("abnormal")].missed_segments.sum() == 21 - m.abnormal_notified_segments
    e = pd.read_csv(OUT / "error_conditions_v2.csv")
    amp = e[e.condition.eq("amp_quartile")]
    assert amp.q25.notna().all() and (amp.boundary_source == "normal_train_segments").all() and amp.unreliable_amp_rows.notna().all()
    # 같은 분할·같은 사분위 이름은 정상·이상에서 같은 경계를 쓴다
    for sid in ("A", "B"):
        g = e[e.split_id.eq(sid) & e.condition.eq("vib_quartile")]
        assert g.q25.nunique() == 1 and g.q75.nunique() == 1


def test_decision_table_is_the_action_rule():
    """판단표는 조치 규칙과 같은 원천(model.DECISION_TABLE)에서 나온다."""
    from model import DECISION_TABLE, ACTIONS, action_for
    t = pd.read_csv(OUT / "decision_table_v2.csv")
    assert t.to_dict("records") == [dict(r) for r in DECISION_TABLE]
    assert set(t.action) == set(ACTIONS.values())
    assert action_for(True, False, False) == ACTIONS["vibration"] and action_for(False, True, False) == ACTIONS["current_magnitude"]
    assert action_for(False, True, True) == ACTIONS["current_magnitude_and_shape"] and action_for(True, True, False) == ACTIONS["vibration_and_current"]


def test_prediction_contract_columns():
    p = pd.read_csv(OUT / "predictions_abnormal_A.csv")
    assert {"model_id", "protocol_version", "criterion", "is_scored", "anomaly_score", "alert_unit", "beyond_calibration_length"} <= set(p.columns)
    assert (p.alert_unit == 0).all() and (p.beyond_calibration_length == 0).all()   # 대회 기록구간은 모두 50행 이하
    assert (p.model_id == "early6_ar2_A").all() and (p.criterion == "conformal").all()
    assert np.allclose(p.anomaly_score, 1 - p.p_value, equal_nan=True) and (p.is_scored == p.score.notna().astype(int)).all()
