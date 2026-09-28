"""검토 1: 보완 실험 계약(press_supplement/contract.errors)의 기기 간 동등성 경로. 사본의 모델 파일을 바꿨다가 되돌린다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_supplement_contract.py
"""
import json, os, shutil, sys
from pathlib import Path
ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "analysis" / "press_supplement"))
import contract
art = ENV / "press_guard" / "artifacts" / "guard_A.json"
backup = art.read_bytes()
try:
    for title, mutate in (("원본", None), ("같은 값·다른 들여쓰기", lambda m: None),
                          ("보정값 하나 상대 +1e-6", lambda m: m["state"]["calibration"].__setitem__(0, m["state"]["calibration"][0] * (1 + 1e-6)))):
        if mutate is not None:
            m = json.loads(backup); mutate(m); art.write_text(json.dumps(m, indent=1))
        notes = []
        bad = contract.errors("E1", contract.HERE, notes=notes)
        print(f"{title:24s} 실패 {bad} | 참고 {[n[:70] for n in notes]}")
finally:
    art.write_bytes(backup)
