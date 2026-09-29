"""검토 8: 4차(8b65130)에서 새로 넣은 시험 15개를 8b65130 사본과 c7d8bba 사본에서 돌린다.

8b65130의 test_time_order.py를 각 사본의 press_guard/ 안에 test_r8_new.py로 복사해 새 시험만 고른다(-k).
c7d8bba에는 CollectionUnits가 없으므로 import 줄에서 뺀 복사본을 쓰고, CollectionUnits 단위 시험은 그 판에서 '실패'로 센다.
저장소는 읽기만 하고, 사본만 쓴다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_newtests.py <8b65130 사본 yejun> <c7d8bba 사본 yejun>
"""
import subprocess
import sys
from pathlib import Path

NEW, OLD = (Path(p).resolve() for p in sys.argv[1:3])
SRC = (NEW / "press_guard" / "test_time_order.py").read_text(encoding="utf-8")
K = ("test_error_row_inside_record_does_not_split_incident or test_error_row_inside_short_normal_record_keeps_second_alert "
     "or test_collection_units_split_only_at_real_gaps_and_isolate_displaced_rows or test_late_stamped_record_end_does_not_merge_incidents "
     "or test_early_stamped_record_start_does_not_merge_incidents")
for name, env in (("8b65130", NEW), ("c7d8bba", OLD)):
    src = SRC if name == "8b65130" else SRC.replace("CollectionUnits, ", "")
    dst = env / "press_guard" / "test_r8_new.py"
    dst.write_text(src, encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA", str(dst), "-k", K],
                       cwd=env / "press_guard", capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("PASSED", "FAILED", "ERROR")) or " passed" in l or " failed" in l]
    print(f"# {name}")
    print("\n".join(lines))
    dst.unlink()
