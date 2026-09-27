"""Claude 후속 구현의 실제 누락/변조 반례. 원본 대신 임시 복사본을 바꾼다."""
import json
import shutil
import numpy as np
import pandas as pd
import pytest
import verify
from model import D, HERE
from contracts import CODE_FILES, training_errors


@pytest.fixture
def copy_run(tmp_path):
    out=tmp_path/"outputs"; art=tmp_path/"artifacts"
    shutil.copytree(HERE/"outputs",out); shutil.copytree(HERE/"artifacts",art)
    return out,art


def update_json(path,update):
    data=json.loads(path.read_text(encoding="utf-8")); update(data); path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("kind",["audit_missing","audit_false","audit_stale","code_missing","summary_changed",
                                  "prediction_missing","figure_missing","analysis_changed","expected_changed"])
def test_integrity_rejects_real_mutations(copy_run,kind):
    out,art=copy_run
    if kind.startswith("audit_"):
        def mutate(d):
            if kind=="audit_missing": d["checks"]=[]
            elif kind=="audit_false": d["checks"][0]["ok"]=False
            else: d["run_fingerprint"]="0"*64
        update_json(out/"audit.json",mutate)
        # 파일 해시를 갱신해도 개별 검사/실행 연결의 논리 검증이 실패해야 한다.
        update_json(out/"manifest.json",lambda d:d.update(audit_sha256=D.sha256_file(out/"audit.json")))
    elif kind=="code_missing": update_json(out/"manifest.json",lambda d:d.update(code_hashes={}))
    elif kind=="summary_changed": update_json(out/"analysis_summary.json",lambda d:d.update(fn_rows_total={"v2":{"A":0,"B":0}}))
    elif kind=="prediction_missing": (out/"predictions_abnormal_A.csv").unlink()
    elif kind=="figure_missing": (out/"fig_first_alarm_v2.png").unlink()
    else:
        f=pd.read_csv(out/"uncertainty_v2.csv"); f.loc[0,"boot_mean"]+=123
        f.to_csv(out/"uncertainty_v2.csv",index=False)
        if kind=="expected_changed": f.to_csv(out/"expected"/"uncertainty_v2.csv",index=False)
    args=["--out",str(out),"--artifacts",str(art)]
    assert verify.main(args)==1
    before=D.sha256_file(out/"expected"/"manifest.json")
    assert verify.main(args+["--freeze"])==2
    assert D.sha256_file(out/"expected"/"manifest.json")==before


def test_analysis_code_is_mandatory(copy_run,tmp_path):
    out,art=copy_run
    code=tmp_path/"code"
    for name in CODE_FILES:
        target=code/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(HERE/name,target)
    (code/"analyze.py").write_text('raise RuntimeError("changed")\n', encoding="utf-8")
    manifest=json.loads((out/"manifest.json").read_text(encoding="utf-8"))
    bad=training_errors(manifest,out,art,code_root=code)
    assert any("analyze.py" in message for message in bad)


@pytest.mark.parametrize("a,b",[(np.nan,np.inf),(np.inf,-np.inf),(1.0000000001,1)])
def test_csv_nonfinite_and_integer_contract(tmp_path,a,b):
    left,right=tmp_path/"left.csv",tmp_path/"right.csv"
    pd.DataFrame({"value":[a]}).to_csv(left,index=False)
    pd.DataFrame({"value":[b]}).to_csv(right,index=False)
    assert not verify.compare_csv(left,right)["ok"]


def test_gain_is_not_only_in_warmup():
    c=pd.read_csv(HERE/"outputs"/"error_conditions_v2.csv")
    c=c[c.alpha.eq(.01)&c.subset.eq("abnormal")&c.condition.eq("pos_bin")]
    for sid,early,late_gain in (("A",26,6),("B",20,4)):
        x=c[c.split_id.eq(sid)].pivot(index="value",columns="model",values="error_rows")
        assert x.loc[["0","1"],"v1"].sum()==early==x.loc[["0","1"],"v2"].sum()
        assert x.loc["≥10","v1"]-x.loc["≥10","v2"]==late_gain


def test_v1_rerun_does_not_break_v2_verify(tmp_path):
    """v1 패키지를 다시 실행하면 v1 manifest의 타이밍·run_id가 바뀐다. v2 검증은 그 파일 해시에 묶이면 안 된다."""
    from contracts import SOURCES, analysis_errors
    manifest=json.loads((HERE/"outputs"/"manifest.json").read_text(encoding="utf-8"))
    root=tmp_path/"src"
    for name in SOURCES:
        target=root/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(HERE.parent/name,target)
    live=root/"press_submission"/"outputs"/"manifest.json"; live.parent.mkdir(parents=True,exist_ok=True)
    original=json.loads((HERE.parent/"press_submission"/"outputs"/"manifest.json").read_text(encoding="utf-8"))
    original["timings_s"]={"total_s":1.0}; original["run_id"]="other+run"
    live.write_text(json.dumps(original), encoding="utf-8")
    assert "press_submission/outputs/manifest.json" not in SOURCES
    assert analysis_errors(manifest,HERE/"outputs",source_root=root)==[]



def test_v1_table_is_compared_with_v1_tolerance(tmp_path):
    """v2 분석은 v1 비교표를 바이트가 아니라 v1 verify 허용오차로 대조한다(평가관 06 R9): LSTM 값 1e-6 차이는 통과, 1e-2는 실패."""
    import importlib.util
    base = HERE.parent / "press_submission"
    spec = importlib.util.spec_from_file_location("press_v1_verify_test", base / "verify.py")
    v1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v1)
    table = pd.read_csv(base / "outputs" / "model_comparison_all.csv")
    lstm = table.index[table.model.astype(str).str.contains("lstm")][0]
    for delta, ok in ((1e-6, True), (1e-2, False)):
        t = table.copy(); t.loc[lstm, "f1_all_rows"] += delta
        path = tmp_path / "model_comparison_all.csv"; t.to_csv(path, index=False)
        assert v1.compare_csv(path, base / "outputs" / "expected" / "model_comparison_all.csv")["ok"] is ok
