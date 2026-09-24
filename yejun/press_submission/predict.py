"""저장된 artifact로 새 입력에 추론한다 (PLAN.md §7). 재학습·재선택은 하지 않는다.

    python predict.py --model artifacts/<model>.json --input new.csv --out predictions.csv

입력 CSV는 TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current 열이 있어야 한다. 그 밖의 열은 무시한다.
출력 열: row_id, record_id, timestamp, status, position_in_record, record_length, is_scored, component scores,
combined_score, p_value, anomaly_score, criterion, budget, alarm, alarm_reason, model_id.
1단계 뼈대 artifact(학습 상태 없음)로 실행하면 점수 열은 비워 두고 status/기록구간만 채운다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from press import data as D  # noqa: E402
from press.artifact import Artifact  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    art = Artifact.load(args.model)
    frame = pd.read_csv(args.input)
    status = D.validate_rows(frame)
    seg = D.segments(frame, status)
    pos, length = D.segment_positions(seg)
    n = len(frame)
    out = pd.DataFrame(dict(row_id=np.arange(n), record_id=seg, timestamp=frame[D.TIME].astype(str), status=status,
                            position_in_record=pos, record_length=length))
    if not art.trained:
        for c in ("score_maxz", "score_sine", "combined_score", "p_value", "anomaly_score", "budget"):
            out[c] = np.nan
        out["is_scored"], out["criterion"], out["alarm"] = 0, "", 0
        out["alarm_reason"] = "no_model_state"
        print(f"경고: {args.model} 에는 학습 상태가 없다(1단계 뼈대). 점수·경보는 비워 둔다.", file=sys.stderr)
    else:
        raise NotImplementedError("학습 상태가 있는 artifact 추론은 2단계에서 구현한다")
    out["model_id"] = art.model_id
    out["protocol_version"] = art.protocol_version
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"{len(out)}행 → {args.out} (기록구간 {len(np.unique(seg))}개, 잘못된 행 {(status != 'ok').sum()}개)")


if __name__ == "__main__":
    main()
