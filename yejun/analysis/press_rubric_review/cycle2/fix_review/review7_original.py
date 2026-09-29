"""검토 7 (e): 시각 오류가 없는 원자료의 예측이 규칙 변경으로 바뀌지 않는가.
대회 정상 평가 구간(A·B)·이상 파일·정상 전체 20,000행(동률 1곳 포함)을 α 1·3·5%로 예측하고, 순서·사건 관련 열과 전체 결정 열의
해시를 적는다. 판마다 돌려 해시를 비교하고, 저장소의 행 단위 예측 파일(사본으로 복사한 것, 07:55 생성, 동결 digest와 SHA-256 같음)과도 대조한다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_original.py [--repo-preds <복사한 예측 폴더>]
"""
import argparse
import hashlib
from pathlib import Path

from review7_lib import *  # noqa: F401,F403

ap = argparse.ArgumentParser()
ap.add_argument("--repo-preds")
args = ap.parse_args()
EXACT = ["row_id", "record_id", "status", "position", "alarm", "reason", "notification", "alert_level", "escalation", "incident_id",
         "incident_notification", "incident_escalation", "incident_update", "time_order_event", "alert_unit", "operating_state"]


def digest(p, cols):
    return hashlib.sha256(p[cols].to_csv(index=False).encode()).hexdigest()[:16]


normal, abnormal = data()
for split in ("A", "B"):
    m = model(split)
    sp = D.split_normal(normal, D.segments(normal), split)
    for alpha in (.01, .03, .05):
        pn, pa = m.predict(sp["test"], alpha), m.predict(abnormal, alpha)
        whole = m.predict(normal, alpha) if alpha == .01 else None
        line = (f"{split} α={alpha}: 정상평가 {len(pn)}행 부호≠0 {int((pn.time_order_event != 0).sum())} 해시 {digest(pn, EXACT)} · "
                f"이상 {len(pa)}행 부호≠0 {int((pa.time_order_event != 0).sum())} 해시 {digest(pa, EXACT)} · 경보 {int(pn.alarm.sum())}/{int(pa.alarm.sum())} "
                f"사건 {int(pn.incident_id.max())}/{int(pa.incident_id.max())} 점수 해시 {digest(pn, ['score', 'p_value'])}/{digest(pa, ['score', 'p_value'])}")
        if whole is not None:
            line += f" · 정상 전체 {len(whole)}행 부호≠0 {int((whole.time_order_event != 0).sum())} 해시 {digest(whole, EXACT)}"
        print(line)
        if args.repo_preds and alpha == .01:
            for name, mine in ((f"predictions_normal_{split}.csv", pn), (f"predictions_abnormal_{split}.csv", pa)):
                ref = pd.read_csv(Path(args.repo_preds) / name, keep_default_na=False)
                cols = [c for c in EXACT if c in ref]
                a = mine[cols].astype(str).reset_index(drop=True)
                b = ref[cols].astype(str).reset_index(drop=True)
                diff = (a != b).any(axis=1).sum()
                sc = np.nanmax(np.abs(mine.score.to_numpy(float) - pd.to_numeric(ref.score, errors="coerce").to_numpy(float)))
                print(f"    저장소 {name}: 결정 열 {len(cols)}개 다른 행 {int(diff)} · 점수 최대 차 {sc:.3g}")
