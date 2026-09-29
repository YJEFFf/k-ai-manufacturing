"""검토 8: 4차 '초안'(사건 단위를 수집 공백 0.5초로만 나누고, 외톨이 첫 행 분리·undo_link가 없는 판)을 8b65130 사본에서 재구성해
새 시험 15개를 돌린다. cycle2 README의 "회귀 시험 7개(초안에서 모두 실패)"를 확인한다. 초안 코드는 커밋되지 않았으므로 재구성이다(추정).

재구성: model.CollectionUnits.step에서 (1) 'or (self.run_rows == 1 and not regular)' 조건을 빼고 (2) displaced를 늘 False로 둔다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_draft.py <8b65130 사본 yejun> <초안을 만들 빈 임시 폴더>
"""
import shutil
import subprocess
import sys
from pathlib import Path

SRC, DST = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
if DST.exists():
    shutil.rmtree(DST)
for sub in ("press_guard", "press_submission"):
    shutil.copytree(SRC / sub, DST / sub)
m = DST / "press_guard" / "model.py"
orig = m.read_text(encoding="utf-8")
a = "if gap is None or gap > UNIT_GAP_S or gap < 0 or (self.run_rows == 1 and not regular):"
b = "displaced = gap is not None and gap > UNIT_GAP_S and self.last_irregular"
assert orig.count(a) == 1 and orig.count(b) == 1
shutil.copy(SRC / "press_guard" / "test_time_order.py", DST / "press_guard" / "test_r8_new.py")
K = ("test_error_row_inside_record_does_not_split_incident or test_error_row_inside_short_normal_record_keeps_second_alert "
     "or test_collection_units_split_only_at_real_gaps_and_isolate_displaced_rows or test_late_stamped_record_end_does_not_merge_incidents "
     "or test_early_stamped_record_start_does_not_merge_incidents")
VARIANTS = {"재구성한 초안(외톨이 첫 행 분리·displaced 둘 다 없음)": orig.replace(a, "if gap is None or gap > UNIT_GAP_S or gap < 0:").replace(b, "displaced = False"),
            "displaced(undo_link)만 뺀 판": orig.replace(b, "displaced = False"),
            "외톨이 첫 행 분리만 뺀 판": orig.replace(a, "if gap is None or gap > UNIT_GAP_S or gap < 0:")}
for name, text in VARIANTS.items():
    m.write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA", "test_r8_new.py", "-k", K],
                       cwd=DST / "press_guard", capture_output=True, text=True)
    print(f"# {name}")
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("PASSED", "FAILED", "ERROR")) or " passed" in l or " failed" in l))
