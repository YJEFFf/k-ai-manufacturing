"""평가관 06 사이클2 3회차 Q6d — 행 단위 예측 동결 요약(predictions_digest.json)의 자기 무결성과 3중 위조 탐침(V6c~V6e, V8a·V8b).

Q6(judge06_Q6_tamper.py)가 만든 작업 사본(Q6_tamper/work/yejun)에서 실행한다. 바꾼 파일은 끝에 모두 되돌린다.
2026-09-28 검수 때 같은 코드를 인라인으로 실행했고 출력은 judge06_Q6_tamper.log 끝에 있다.

    cd <J06_BASE>/Q6_tamper/work/yejun && OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python <이 파일>
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, "press_guard")
import verify  # noqa: E402

OUT = Path("press_guard/outputs"); EXP = OUT / "expected"
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run():
    p = subprocess.run([sys.executable, "press_guard/verify.py"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    lines = [l.strip() for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    return p.returncode, lines[-1][:140], [l[:150] for l in lines if l.startswith("FAIL")]


def main():
    files = [OUT / "manifest.json", OUT / "test_predictions_A.csv", OUT / "workload_v2.csv", EXP / "workload_v2.csv", EXP / "predictions_digest.json"]
    saved = {f: f.read_bytes() for f in files}
    F = EXP / "predictions_digest.json"
    orig = saved[F]
    try:
        # V6c~V6e: 동결 요약 필드 손상(결과 파일은 그대로)
        d = json.loads(orig); d["test_predictions_A.csv"]["sha256"] = "0" * 64; F.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[V] V6c 동결 요약의 test_predictions_A sha256을 0으로:", run()[:2])
        d = json.loads(orig); d["test_predictions_A.csv"]["exact_sha256"] = "0" * 64; F.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[V] V6d 동결 요약의 exact_sha256만 0으로:", run()[:2])
        d = json.loads(orig); d["test_predictions_A.csv"]["sha256"] = "0" * 64; d["test_predictions_A.csv"]["exact_sha256"] = "0" * 64
        F.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[V] V6e sha256·exact_sha256 둘 다 0으로:", run()[:2])
        F.write_bytes(orig)
        # V8a: 결과 CSV 3중 위조(workload_v2 한 칸 +1 + 실행 기록 해시 + 동결 사본)
        x = pd.read_csv(OUT / "workload_v2.csv"); c = [k for k in x.columns if pd.api.types.is_float_dtype(x[k])][0]; x.loc[0, c] += 1.0
        x.to_csv(OUT / "workload_v2.csv", index=False); x.to_csv(EXP / "workload_v2.csv", index=False)
        m = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
        for grp in (m.get("analysis", {}).get("outputs", {}), m.get("outputs", {})):
            if "workload_v2.csv" in grp:
                grp["workload_v2.csv"] = sha(OUT / "workload_v2.csv")
        (OUT / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[V] V8a 결과 CSV 3중 위조:", run())
        for f in files:
            f.write_bytes(saved[f])
        # V8b: 행 단위 예측 3중 위조(정상 행 경보 0→1 + 실행 기록 해시 + 동결 요약 재계산)
        x = pd.read_csv(OUT / "test_predictions_A.csv"); i = int(x.index[(x.label == 0) & (x.alarm == 0)][100]); x.loc[i, "alarm"] = 1
        x.to_csv(OUT / "test_predictions_A.csv", index=False)
        m = json.loads((OUT / "manifest.json").read_text(encoding="utf-8")); m["outputs"]["test_predictions_A.csv"] = sha(OUT / "test_predictions_A.csv")
        (OUT / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        d = json.loads(orig); d["test_predictions_A.csv"] = verify.prediction_digest(OUT / "test_predictions_A.csv")
        F.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[V] V8b 행 단위 예측 3중 위조(행 {i}):", run())
    finally:
        for f in files:
            f.write_bytes(saved[f])
    print("[V] 되돌림 뒤:", run()[:2])


if __name__ == "__main__":
    main()
