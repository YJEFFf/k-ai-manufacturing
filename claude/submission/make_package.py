"""제출용 코드 패키지(submission/북적북적_code/)와 압축 파일(북적북적_code.zip)을 만든다.

입력: 볼트 code/press/(우리 코드), 팀 레포 yejun/(팀원 모듈), 볼트 data/3_소성가공_예지보전/(원본 CSV 2개),
      submission/package_files/(run_all.py, README.md, requirements.txt, environment.yml)
출력: submission/북적북적_code/, submission/북적북적_code.zip, 패키지 안 expected_results.json(보고서 작성 때의 결과값)
실행: python submission/make_package.py --repo <팀 레포 클론 경로>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
PRESS = PROJ / "code" / "press"
NAME = "북적북적_code"
# 산출물·캐시·웹·문서·시험 폴더는 넣지 않는다(실행하면 다시 생긴다)
SKIP_DIRS = {"__pycache__", ".pytest_cache", "outputs", "cache", "web", "docs", "tests", ".omc"}
# 실행에 안 쓰는 팀 내부 작업 지시 문서(보고서 수치와 다른 옛 수치가 적혀 있어 심사에서 혼동을 준다)
SKIP_FILES = {"요청사항_준용.md", "STORYLINE.md"}   # STORYLINE.md: 팀 내부 보고서 구성 협의 문서
# 팀원 v3 코드(core.py)가 import할 때 읽는 protocol.json이 있는 폴더
MASTER_PLAN = Path("plans") / "press_master_2026-10-03"


def long_path(p: Path) -> str:
    """윈도우 260자 경로 제한 우회(\\\\?\\ 접두). 팀원 분석 폴더의 파일 경로가 이 한도를 넘는다."""
    return "\\\\?\\" + str(p.resolve())


def is_env_file(name: str) -> bool:
    """팀원 폴더의 환경 파일(파이썬 3.12·numpy 1.26.4 고정). 패키지는 루트의 3.13 환경 파일 하나로 맞춘다."""
    return name == "environment.yml" or (name.startswith("requirements") and name.endswith(".txt"))


def copy_tree(src: Path, dst: Path, skip_dirs=SKIP_DIRS, skip_prefix=("test_",)):
    """src 아래 파일을 dst로 복사한다. 제외 폴더·접두어·캐시 파일·환경 파일은 건너뛴다."""
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if (p.is_dir() or skip_dirs & set(rel.parts[:-1]) or p.name.startswith(skip_prefix)
                or p.suffix in (".pyc", ".log", ".pkl") or is_env_file(p.name) or p.name in SKIP_FILES):
            continue
        out = dst / rel
        Path(long_path(out.parent)).mkdir(parents=True, exist_ok=True)
        shutil.copy2(long_path(p), long_path(out))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_lf(p: Path) -> str:
    """run_all.py와 같은 규칙: 줄바꿈을 LF로 맞춘 뒤의 해시(OS마다 다른 CSV 줄바꿈을 무시)."""
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def csv_value(path, where, column):
    """CSV에서 where 조건(열=값)에 맞는 첫 행의 column 값."""
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if all(str(r[k]) == str(v) for k, v in where.items()):
                return float(r[column])
    raise KeyError((path, where))


def build_expected():
    """run_all.py가 대조할 기준값. quick=True 항목은 --quick 실행에서도 확인한다."""
    tvt, cases, dom = PRESS / "tvt" / "outputs", PRESS / "cases" / "outputs", PRESS / "domain" / "outputs"
    meta = json.loads((tvt / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    checks = []
    for s in ("A", "B"):
        checks.append(dict(name=f"기반 모델 v2 원래 평가 재현 F1 {s}", kind="json", file="code/press/tvt/outputs/tvt_scores_meta.json",
                           path=[s, "v2_original_protocol", "f1"], value=meta[s]["v2_original_protocol"]["f1"], quick=True, report="(6장)"))
    # LSTM은 학습 난수 때문에 값이 조금 흔들려 허용 오차를 넓게 둔다
    for model, label, tol, rep in (("v2+H1+H2", "2단계 모델 v2+R1+R2", 1e-9, "(2.4절 표)"), ("v2+H1", "잠금 모델 v2+R1(공식 성능)", 1e-9, "(2.4절 표·2.5절)"),
                                   ("v2", "기반 모델 v2", 1e-9, "(2.4절 표)"), ("lstm20", "LSTM 오토인코더", 0.05, "(2.4절 표, 학습 난수로 소폭 변동 가능)")):
        for s in ("A", "B"):
            where = dict(split=s, alpha="0.01", model=model, mode="realtime")
            checks.append(dict(name=f"test 실시간 행 F1 {label} {s}", kind="csv", file="code/press/tvt/outputs/tvt_test.csv",
                               where=where, column="f1", value=csv_value(tvt / "tvt_test.csv", where, "f1"), tol=tol, quick=True, report=rep))
    # 제출 예측 파일은 숫자 비교가 아니라 바이트 단위(sha256)로 같아야 한다
    for s in ("A", "B"):
        checks.append(dict(name=f"제출 test 예측 파일 {s}(줄바꿈을 맞춘 바이트 동일)", kind="sha256", file=f"predictions/test_predictions_{s}.csv",
                           value=sha256_lf(tvt / f"test_predictions_{s}.csv"), quick=True, report="(제출물)"))
    fx = json.loads((cases / "facts_extra.json").read_text(encoding="utf-8"))
    checks.append(dict(name="형식 누수: 자릿수 규칙 행 F1(원본)", kind="json", file="code/press/cases/outputs/facts_extra.json",
                       path=["format_leak", "raw", "f1"], value=fx["format_leak"]["raw"]["f1"], quick=True, report="(1.6절)"))
    # 여기부터는 전체 실행에서만 확인
    vs = json.loads((tvt / "validation_summary.json").read_text(encoding="utf-8"))
    checks.append(dict(name="검증 V1b: R2 진동 단독 주입 최대 손실(%p)", kind="json", file="code/press/tvt/outputs/validation_summary.json",
                       path=["judgments", "V1b_max_cost_pp"], value=vs["judgments"]["V1b_max_cost_pp"], tol=1e-6, report="(2.6절)"))
    ph = json.loads((dom / "01_signal_physics.json").read_text(encoding="utf-8"))
    checks.append(dict(name="정상 전류 겉보기 주파수 중앙값(Hz)", kind="json", file="code/press/domain/outputs/01_signal_physics.json",
                       path=["1_alias_sampling_interval", "normal_records_ge30", "f_alias", "median"],
                       value=ph["1_alias_sampling_interval"]["normal_records_ge30"]["f_alias"]["median"], report="(1.4절)"))
    seq = dom / "04_sequential_uncertainty.csv"
    for key, name, rep in (("v2+H1+H2", "순차 검출 비교표의 2단계 모델 test F1 B", "(2.5절)"), ("CUSUM-carry", "CUSUM(상태 유지) test F1 B", "(2.7절 표)")):
        where = dict(key=key, split="B", regime="test")
        checks.append(dict(name=name, kind="csv", file="code/press/domain/outputs/04_sequential_uncertainty.csv",
                           where=where, column="f1", value=csv_value(seq, where, "f1"), report=rep))
    for model, label in (("v2", "v2"), ("v2+H2", "v2+R2")):
        where = dict(scheme="gmm", grouping="state", split="B", alpha="0.05", part="valid+test", state="busy_high", model=model)
        checks.append(dict(name=f"분할 B 고부하 정상 오경보 기록 {label}(α 5%)", kind="csv", file="code/press/domain/outputs/06_operating_regime.csv",
                           where=where, column="fa_records", value=csv_value(dom / "06_operating_regime.csv", where, "fa_records"), report="(3.2절 표)"))
    # 기록 하나를 1개로 센 F1(사후, 2.4절 표 † 열)
    for model, label in (("v2", "기반 모델 v2"), ("v2+H1+H2", "2단계 모델 v2+R1+R2")):
        where = dict(split="B", regime="test", model=model)
        checks.append(dict(name=f"test 기록 수 F1 {label} B", kind="csv", file="code/press/tvt/outputs/tvt_record_count.csv",
                           where=where, column="rec_f1", value=csv_value(tvt / "tvt_record_count.csv", where, "rec_f1"), quick=True, report="(2.4절 표 †)"))
    # 이상 기록 양상(domain/07, 사후, 4.2절): 상·하부 진동이 모두 큰 기록 수
    ap_ = json.loads((dom / "07_anomaly_patterns.json").read_text(encoding="utf-8"))
    checks.append(dict(name="이상 양상: 상·하부 진동 모두 큰 기록 수", kind="json", file="code/press/domain/outputs/07_anomaly_patterns.json",
                       path=["counts", "상·하부 진동 모두 큼"], value=ap_["counts"]["상·하부 진동 모두 큼"], report="(4.2절)"))
    # 이상 확률(08, valid로만 보정): test Brier(파일 이상 비율을 사전으로)
    pr = json.loads((tvt / "tvt_probability.json").read_text(encoding="utf-8"))
    checks.append(dict(name="이상 확률 test Brier B(파일 비율 사전)", kind="json", file="code/press/tvt/outputs/tvt_probability.json",
                       path=["B", "brier_fileprior"], value=pr["B"]["brier_fileprior"], tol=1e-6, quick=True, report="(2.5절)"))
    # R1을 기준선에도 붙인 비교(사후, 2.7절)와 LSTM 창 때문에 점수 없는 행
    for model, col, label in (("iforest+H1", "test_f1", "IsolationForest+R1 test F1 B"), ("knn5+H1", "test_fp", "5NN+R1 test 오경보 행 B")):
        where = dict(split="B", model=model)
        checks.append(dict(name=label, kind="csv", file="code/press/tvt/outputs/tvt_r1_baselines.csv", where=where, column=col,
                           value=csv_value(tvt / "tvt_r1_baselines.csv", where, col), quick=True, report="(2.7절 †)"))
    where = dict(split="A", model="lstm20")
    checks.append(dict(name="LSTM 20행 창 때문에 점수 없는 test 이상 행 A", kind="csv", file="code/press/tvt/outputs/tvt_unscored.csv", where=where,
                       column="no_score_rows", value=csv_value(tvt / "tvt_unscored.csv", where, "no_score_rows"), quick=True, report="(2.4절)"))
    # 문턱과 무관한 비교(10, 사후, 2.4절 †): R1 없는 test 행 AUROC와 v2−v1 F1 차이의 부트스트랩 하한
    for s_ in ("A", "B"):
        where = dict(split=s_, model="v2")
        checks.append(dict(name=f"test 행 AUROC 기반 모델 v2 {s_}(R1 없이)", kind="csv", file="code/press/tvt/outputs/threshold_free.csv",
                           where=where, column="auroc", value=csv_value(tvt / "threshold_free.csv", where, "auroc"), tol=1e-9, quick=True, report="(2.4절 †)"))
    where = dict(split="B", other="v1")
    checks.append(dict(name="부트스트랩 v2−v1 F1 차이 95% 하한 B", kind="csv", file="code/press/tvt/outputs/threshold_free_boot.csv",
                       where=where, column="d_f1_lo", value=csv_value(tvt / "threshold_free_boot.csv", where, "d_f1_lo"), tol=1e-6, quick=True, report="(2.4절 †)"))
    # 사후 보조 수치(11, 2.5·2.7·4.3절)
    ph = json.loads((tvt / "posthoc_numbers.json").read_text(encoding="utf-8"))
    for path, label, rep in ((["maxz_rules", "A|maxz3+H1+H2|0.01", "valid_f1"], "max|z|+R1+R2 valid 실시간 F1 A(α 1%)", "(2.7절 † R1 표)"),
                             (["maxz_rules", "B|maxz3+H1+H2|0.05", "test_fp"], "max|z|+R1+R2 test 오경보 행 B(α 5%)", "(2.7절 †)"),
                             (["probability", "A|v2_prob_fileprior", "auroc"], "이상 확률 test 행 AUROC A", "(2.5절)"),
                             (["gaps", "median_s"], "정상 파일 수집 공백 중앙값(초)", "(4.3절)")):
        v = ph
        for k in path:
            v = v[k]
        checks.append(dict(name=label, kind="json", file="code/press/tvt/outputs/posthoc_numbers.json", path=path, value=v, tol=1e-9,
                           quick=True, report=rep))
    # 합성 열화(12, 사후, 4.3절)
    rs = json.loads((tvt / "ramp_summary.json").read_text(encoding="utf-8"))
    for key, col, label in (("전류 파형|10분|v2+R1+R2", "lead_median_min", "합성 열화 10분 전류 파형 선행 시간 중앙값(분)"),
                            ("진동|5분|v2+R1+R2", "before_complete_rate", "합성 열화 5분 진동 완성 전 경보 비율")):
        checks.append(dict(name=label, kind="json", file="code/press/tvt/outputs/ramp_summary.json", path=[key, col],
                           value=rs[key][col], tol=1e-9, quick=True, report="(4.3절)"))
    # R2 준-표본 밖(13, 사후, 2.5절 †)과 Ridge 예측 오차(14, 사후, 2.4절 †): 전체 실행
    ro = json.loads((tvt / "r2_oos_alpha.json").read_text(encoding="utf-8"))
    rj = json.loads((tvt / "ridge_baseline.json").read_text(encoding="utf-8"))
    fb = json.loads((tvt / "record_auroc_featbase.json").read_text(encoding="utf-8"))
    jc = json.loads((tvt / "jitter_ridge_combo.json").read_text(encoding="utf-8"))
    for f, js, path, label, rep in (
            ("r2_oos_alpha.json", ro, ["A_r2_out_of_sample", "0.05", "rolling_total", "keep|v2"], "R2 준-표본 밖: α 5% 정상 오경보 기록 v2(시간순 5창, 착안 기록 제외)", "(2.5절 †)"),
            ("r2_oos_alpha.json", ro, ["A_r2_out_of_sample", "0.05", "rolling_total", "keep|v2+R2"], "R2 준-표본 밖: α 5% 정상 오경보 기록 v2+R2", "(2.5절 †)"),
            ("ridge_baseline.json", rj, ["ridge", "B", "ridge", "test_f1"], "Ridge 예측 오차 test 실시간 F1 B(R1 없이)", "(2.7절 †)"),
            ("record_auroc_featbase.json", fb, ["featbase_rows", "B", "knn5_feat", "test_f1"], "v2 특징을 넣은 5NN test 실시간 F1 B(R1 없이)", "(2.4·2.7절 †)"),
            ("jitter_ridge_combo.json", jc, ["A_jitter", "sigma_ms_reaching_abnormal_r2"], "정상 R² 중앙값이 이상 수준에 닿는 표본 시각 흔들림(ms)", "(2.6절 †)"),
            ("jitter_ridge_combo.json", jc, ["B_combo", "high_load_B_a5_valid_test", "v2+R1|ridge", "all_fa_records"], "1단계 병행(v2+R1 OR Ridge) α 5% 정상 오경보 기록 B", "(4.3절 †)")):
        v = js
        for k in path:
            v = v[k]
        checks.append(dict(name=label, kind="json", file=f"code/press/tvt/outputs/{f}", path=path, value=v, tol=1e-9, report=rep))
    # 성분 절제(09, 사후, 2.4절 †): 분할 B 전류 파형 주입 강도 1의 크기 성분만 / v2 탐지율(전체 실행)
    for col, label in (("크기", "크기 성분만"), ("v2", "v2(세 성분)")):
        where = dict(split="B", family="current_residual", target="2", strength="1.0")
        checks.append(dict(name=f"성분 절제: 전류 파형 주입 강도 1 탐지율 {label} B", kind="csv", file="code/press/tvt/outputs/ablation_pod.csv",
                           where=where, column=col, value=csv_value(tvt / "ablation_pod.csv", where, col), tol=1e-9, report="(2.7절 †)"))
    return dict(note="보고서 작성 때(2026-10-04) 볼트 산출물에서 뽑은 값. run_all.py가 실행 뒤 같은 위치의 값과 비교한다",
                checks=checks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True, help="팀 레포 클론 경로(yejun/ 포함)")
    a = ap.parse_args()
    stage = HERE / NAME
    if stage.exists():
        shutil.rmtree(long_path(stage))
    stage.mkdir()
    # 우리 코드: "_"로 시작하는 파일은 작업용 초안이라 뺀다
    for sub in ("cases", "tvt", "domain"):
        copy_tree(PRESS / sub, stage / "code" / "press" / sub, skip_prefix=("_",))
    shutil.copy2(PRESS / "06_alias_frequency_audit.py", stage / "code" / "press" / "06_alias_frequency_audit.py")
    # 팀원 모듈(레포와 같은 yejun/ 상대 위치를 지켜야 팀원 코드의 경로 계산이 맞는다)
    y = a.repo / "yejun"
    for rel in ("press_guard", "analysis/press_master_validation_2026-10-03", "analysis/press_evidence"):
        copy_tree(y / rel, stage / "yejun" / rel)
    # v3 모듈(core.py)이 읽는 설계 파일만 넣는다. 같은 폴더의 계획·검토 문서(md)와 외부 자료 수집 기록은 실행에 쓰지 않아 뺀다
    (stage / "yejun" / MASTER_PLAN).mkdir(parents=True)
    for f in ("protocol.json", "execution_revision.json", "execution_contracts.json"):
        shutil.copy2(y / MASTER_PLAN / f, stage / "yejun" / MASTER_PLAN / f)
    # 보완 LSTM 실험(보고서 2.7절 †, run_all.py 밖): 코드와 결과 표(outputs)를 넣고 가중치 캐시(cache)는 뺀다
    copy_tree(y / "analysis" / "press_lstm_improvement", stage / "yejun" / "analysis" / "press_lstm_improvement",
              skip_dirs=SKIP_DIRS - {"outputs"})
    # 원본 데이터는 run_all.py가 해시 확인 뒤 이 폴더에 다시 배치하므로 빼 둔다
    copy_tree(y / "press_submission", stage / "yejun" / "press_submission", skip_dirs=SKIP_DIRS | {"data"})
    # 원본 데이터
    (stage / "data" / "3_소성가공_예지보전").mkdir(parents=True)
    for f in ("press_data_normal.csv", "outlier_data.csv"):
        shutil.copy2(PROJ / "data" / "3_소성가공_예지보전" / f, stage / "data" / "3_소성가공_예지보전" / f)
    # 실행 파일·문서·환경 파일(파이썬 3.13)
    for f in (HERE / "package_files").iterdir():
        shutil.copy2(f, stage / f.name)
    # 제출 예측 파일(공고 필수 "테스트데이터 예측결과 파일"). run_all.py도 실행 끝에 같은 파일을 다시 만든다
    (stage / "predictions").mkdir()
    for s in ("A", "B"):
        shutil.copy2(PRESS / "tvt" / "outputs" / f"test_predictions_{s}.csv", stage / "predictions" / f"test_predictions_{s}.csv")
    (stage / "expected_results.json").write_text(json.dumps(build_expected(), ensure_ascii=False, indent=2), encoding="utf-8")
    # 압축: 최상위 폴더 이름을 북적북적_code로 둔다
    zpath = HERE / f"{NAME}.zip"
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(long_path(p), str(Path(NAME) / p.relative_to(stage)))
    print(f"패키지: {stage} ({len(files)}개 파일), 압축: {zpath} ({zpath.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
