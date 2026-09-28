"""실제 데이터의 관측 접두부와 모의 화면의 건·사건·조치가 일치해야 한다."""
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from model import D, HERE, layout
from serve import Console


def test_browser_simulation_matches_independently_scored_prefixes():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node가 있으면 실제 app.js의 접두부 집계를 추가 검증한다")
    console = Console()
    normal = D.inputs_only(D.split_normal(console.normal, D.segments(console.normal), "B")["test"])
    segment = layout(normal)[1]
    parts, start = [], pd.Timestamp("2022-07-12T00:00:00")
    for record in (0, 3, 41, 0):
        part = normal.loc[segment == record].reset_index(drop=True).copy()
        part[D.TIME] = (start + pd.to_timedelta(np.arange(len(part)) * .1, unit="s")).astype(str)
        start += pd.Timedelta(seconds=(len(part) - 1) * .1 + 2)
        parts.append(part)
    # 긴 연속 기록에서는 아직 경보가 없는 다음 50행 블록을 미래 건에 미리 포함하면 안 된다.
    abnormal = D.inputs_only(console.abnormal).reset_index(drop=True).copy()
    abnormal[D.TIME] = (start + pd.to_timedelta(np.arange(len(abnormal)) * .1, unit="s")).astype(str)
    # 과거 시각으로 돌아간 행은 정상 복귀 창으로 취급하지 않는다.
    recovered = parts[0].copy()
    resume = pd.Timestamp(abnormal[D.TIME].iloc[-1]) + pd.Timedelta(seconds=2)
    recovered[D.TIME] = (resume + pd.to_timedelta(np.arange(len(recovered)) * .1, unit="s")).astype(str)
    # 경보 기록(3) 바로 뒤의 경보 없는 +1시간 튄 한 행: 튄 것으로 확인되기 전·후 모두 품질 시간창 경계가 두 구현에서 같아야 한다.
    spike = parts[2].iloc[[5]].copy()
    spike[D.TIME] = str(pd.Timestamp(parts[1][D.TIME].iloc[-1]) + pd.Timedelta(hours=1))
    frame = pd.concat(parts[:2] + [spike] + parts[2:] + [abnormal, parts[0], recovered], ignore_index=True)
    spike_at = len(parts[0]) + len(parts[1])

    def analyze(data):
        return console.analyze(dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=data.to_csv(index=False)))

    full = analyze(frame)
    assert full["points"][spike_at + 1]["time_order_event"] == 2
    cutoffs = {0, len(parts[0]) - 1, len(frame) - 1, spike_at, spike_at + 1}
    reverse_start = sum(map(len, parts)) + 1 + len(abnormal)
    cutoffs.update((reverse_start - 1, reverse_start, reverse_start + len(parts[0]) - 1))
    for case in full["cases"]:
        cutoffs.update((case["first_row"] - 1, case["first_row"], case["row_to"]))
    for incident in full["incidents"]:
        if incident["escalation_row"] is not None:
            cutoffs.add(int(incident["escalation_row"]))
    cutoffs.update(range(sum(map(len, parts)) + 1 + 49, len(frame), 50))
    prefixes = []
    for cursor in sorted(cutoffs):
        result = analyze(frame.iloc[:cursor + 1])
        prefixes.append(dict(cursor=cursor, cases=result["cases"], incidents=result["incidents"], alarm_rows=result["stats"]["alarm_rows"]))
    result = subprocess.run([node, str(HERE / "test_web_prefix.cjs")], input=json.dumps(dict(full=full, prefixes=prefixes)),
                            text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
