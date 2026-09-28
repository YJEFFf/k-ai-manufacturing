"""review4: review4_jitter_features.py의 B 평가 구간판(시작 기록 420)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np, pandas as pd
import review4_jitter_features as F  # 모듈 실행 시 A 표가 먼저 출력된다
normB = F.split_records(F.n, F.rn, 17, first=420)
rows = {"정상 B 평가(길이≥17)": F.table(normB), "정상 B 평가 + 60.6 Hz 2.4 ms": F.table(F.jitter(normB, 60.6, 2.4))}
print(pd.DataFrame(rows).T.to_string())
