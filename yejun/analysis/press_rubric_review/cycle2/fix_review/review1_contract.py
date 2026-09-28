"""검토 1: 분석 패키지 계약(analysis/package_contract.py)과 동등성(press_guard/equivalence.py) 반례.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_contract.py
모든 변조는 임시 폴더의 사본에만 한다.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
import numpy as np
import pandas as pd


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


pc = load("pc", ENV / "analysis" / "package_contract.py")
eq = load("eq", ENV / "press_guard" / "equivalence.py")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def csv_case(title, a_rows, b_rows, columns, tol=1e-9, overrides=None):
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "now.csv", Path(tmp) / "frozen.csv"
        pd.DataFrame(a_rows, columns=columns).to_csv(a, index=False)
        pd.DataFrame(b_rows, columns=columns).to_csv(b, index=False)
        r = pc.compare_csv(a, b, tol, overrides)
        print(f"  {title:58s} → {'통과' if r is None else '실패: ' + r}")


def part_a():
    print("## A. package_contract.compare_csv 문자 열의 수치 비교")
    csv_case("문자 열 '007' vs '7'(식별자 자릿수)", [["x", "007"]], [["x", "7"]], ["k", "id"])
    csv_case("문자 열 '1.10' vs '1.1'(판 번호)", [["x", "1.10"]], [["x", "1.1"]], ["k", "version"])
    csv_case("문자 열 '0.970990' vs '0.97099'", [["x", "0.970990"]], [["x", "0.97099"]], ["k", "value"])
    csv_case("문자 열 '21/21' vs '20/21'", [["x", "21/21"]], [["x", "20/21"]], ["k", "value"])
    csv_case("문자 열 '5' vs ' 5'(앞 공백)", [["x", " 5"]], [["x", "5"]], ["k", "value"])
    csv_case("문자 열 'nan' vs 'NaN'", [["x", "nan"]], [["x", "NaN"]], ["k", "value"])
    csv_case("수치 열 1e9 vs 1e9+0.9(상대 1e-9)", [[1e9 + 0.9]], [[1e9]], ["v"])
    csv_case("정수 열 3000000000 vs 3000000002", [[3000000002]], [[3000000000]], ["count"])
    csv_case("override 열(spearman 1e-4) 0.9 vs 0.90009", [[0.90009]], [[0.9]], ["spearman"], overrides={"spearman": 1e-4})
    print("## B. json_close")
    for title, p, q in (("bool True vs 정수 1", {"a": True}, {"a": 1}), ("정수 1 vs 실수 1.0", {"a": 1}, {"a": 1.0}),
                        ("큰 정수 1.7e12 vs +1000", {"t": 1_700_000_001_000}, {"t": 1_700_000_000_000}),
                        ("None vs 0", {"a": None}, {"a": 0})):
        print(f"  {title:58s} → {'같음' if pc.json_close(p, q, 1e-9) else '다름'}")


def part_c():
    print("## C. equivalent_dependency / artifact_equivalent 변조(임시 사본)")
    with tempfile.TemporaryDirectory() as tmp:
        g = Path(tmp) / "press_guard"
        (g / "outputs" / "expected").mkdir(parents=True); (g / "artifacts").mkdir()
        src = ENV / "press_guard"
        shutil.copy2(src / "equivalence.py", g / "equivalence.py")
        for n in ("guard_A.json",):
            shutil.copy2(src / "outputs" / "expected" / n, g / "outputs" / "expected" / n)
        for n in ("rolling.csv", "metrics.csv"):
            shutil.copy2(src / "outputs" / "expected" / n, g / "outputs" / "expected" / n)
        pc.GUARD = g
        frozen_model = json.loads((g / "outputs" / "expected" / "guard_A.json").read_text())
        recorded = sha(g / "outputs" / "expected" / "guard_A.json")

        def try_model(title, mutate, envelope_fix=False):
            m = json.loads(json.dumps(frozen_model))
            mutate(m)
            p = g / "artifacts" / "guard_A.json"
            p.write_text(json.dumps(m, ensure_ascii=False, indent=1))
            r = pc.equivalent_dependency(p, recorded)
            print(f"  모델 {title:52s} → {'통과(참고)' if r else '실패'}")

        def cal(k, rel):
            def f(m):
                m["state"]["calibration"][k] *= (1 + rel)
            return f
        try_model("같은 값, 들여쓰기만 다름", lambda m: None)
        try_model("보정값 한 개 상대 +5e-9", cal(0, 5e-9))
        try_model("보정값 한 개 상대 +1e-6", cal(0, 1e-6))
        try_model("AR 계수 상대 +1e-7", lambda m: m["state"]["ar2"].__setitem__(1, m["state"]["ar2"][1] * (1 + 1e-7)))
        try_model("문자 필드(selection) 변경", lambda m: m["state"].__setitem__("selection", "x"))
        try_model("키 하나 삭제(sampling_seconds)", lambda m: m["state"].pop("sampling_seconds"))
        try_model("봉투 sha256만 변조(상태 그대로 → 불러오기는 실패할 파일)", lambda m: m.__setitem__("sha256", "0" * 64))

        def try_csv(title, name, mutate):
            f = pd.read_csv(g / "outputs" / "expected" / name)
            mutate(f)
            p = g / "outputs" / name
            f.to_csv(p, index=False, float_format="%.17g")
            r = pc.equivalent_dependency(p, sha(g / "outputs" / "expected" / name))
            print(f"  결과 CSV {name} {title:40s} → {'통과(참고)' if r else '실패'}")

        num = lambda f: [c for c in f.columns if pd.api.types.is_float_dtype(f[c])][0]
        try_csv("같은 값, 17자리 표기", "rolling.csv", lambda f: None)
        try_csv("실수 한 칸 +1e-6", "rolling.csv", lambda f: f.__setitem__(num(f), f[num(f)].where(f.index != 0, f[num(f)] + 1e-6)))
        try_csv("정수 한 칸 +1", "metrics.csv", lambda f: f.__setitem__([c for c in f.columns if pd.api.types.is_integer_dtype(f[c])][0],
                                                                     f[[c for c in f.columns if pd.api.types.is_integer_dtype(f[c])][0]] + (f.index == 0)))
        # 동결 사본 해시가 기록과 다르면(다른 실행의 동결) 동등성으로 봐 주지 않아야 한다
        p = g / "artifacts" / "guard_A.json"; p.write_text(json.dumps(frozen_model, indent=1))
        print("  기록 해시가 동결 사본과 다를 때(다른 실행) →", "통과(참고)" if pc.equivalent_dependency(p, "0" * 64) else "실패")


if __name__ == "__main__":
    part_a()
    part_c()
