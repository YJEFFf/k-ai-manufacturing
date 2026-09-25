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
    a = json.loads((art / "guard_A.json").read_text()); a["state"]["ar2"][0] += 1; (art / "guard_A.json").write_text(json.dumps(a))
    assert verify.main(["--out", str(out), "--artifacts", str(art)]) == 1
    assert verify.main(["--out", str(out), "--artifacts", str(art), "--freeze"]) == 2
