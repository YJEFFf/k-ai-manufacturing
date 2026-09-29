"""J4 위원 독립 점검 5: j4_independent_v2.py의 같은 구현(팀 코드 미사용)으로 시간순 5겹(README 66~69행)을 다시 계산한다.

겹 정의(press_evidence README O1(a)): 평가 60구간 [s, s+60), 보정 직전 120구간 [s-120, s), 학습 [0, s-120).
README 주장: F1 0.961938~0.971819, 정상 알림 0·0·2·0·0/60(α=1%).
실행: python j4_independent_rolling.py <원본 데이터 폴더>   결과: j4_independent_rolling.json
"""
import json
import sys
from pathlib import Path

src = Path(__file__).with_name("j4_independent_v2.py").read_text(encoding="utf-8")
defs = src.split("seg_n, seg_a = records(normal), records(abnormal)")[0]
ns = {"__name__": "j4_defs"}
exec(compile(defs, "j4_independent_v2_defs", "exec"), ns)
np, pd = ns["np"], ns["pd"]
normal, abnormal, records, J4Guard = ns["normal"], ns["abnormal"], ns["records"], ns["J4Guard"]
seg_n, seg_a = records(normal), records(abnormal)
res = {}
for s in (300, 360, 420, 480, 540):
    tr, cal, te = seg_n < s - 120, (seg_n >= s - 120) & (seg_n < s), (seg_n >= s) & (seg_n < s + 60)
    g = J4Guard(normal[tr].reset_index(drop=True), seg_n[tr])
    sc = g.score(normal[cal].reset_index(drop=True), seg_n[cal])
    ref = np.sort(pd.Series(np.where(np.isfinite(sc), sc, -np.inf)).groupby(seg_n[cal]).max().to_numpy())

    def p(v):
        out = np.full(len(v), np.nan)
        ok = np.isfinite(v)
        out[ok] = (len(ref) - np.searchsorted(ref, v[ok], side="left") + 1) / (len(ref) + 1)
        return out

    an = p(g.score(normal[te].reset_index(drop=True), seg_n[te])) <= 0.01
    aa = p(g.score(abnormal, seg_a)) <= 0.01
    tp, fn, fp = int(aa.sum()), int((~aa).sum()), int(an.sum())
    res[f"{s}-{s + 59}"] = dict(f1=round(2 * tp / (2 * tp + fn + fp), 6), tp=tp, fn=fn, fp=fp,
                                normal_records_alerted=f"{int(pd.Series(an).groupby(seg_n[te]).any().sum())}/60",
                                abnormal_records_detected=f"{int(pd.Series(aa).groupby(seg_a).any().sum())}/21")
Path(__file__).with_name("j4_independent_rolling.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
