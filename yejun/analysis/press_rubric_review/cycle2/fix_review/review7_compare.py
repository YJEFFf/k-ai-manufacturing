"""검토 7: 세 판(c7d8bba·3c6fbf3·110afa2)의 상황표 결과(review7_scenarios.py 출력 jsonl)를 나란히 놓는다."""
import json, sys
paths = dict(arg.split("=") for arg in sys.argv[1:])
data = {v: {r["sid"]: r for r in map(json.loads, open(p))} for v, p in paths.items()}
vs = list(paths)
key = ("held", "c2", "c3", "c4", "body_alarm_loss", "body_incidents", "starts", "escalations", "dup_alerts")
def fmt(r):
    return f"보류{r['held']} 부호2·3·4={r['c2']}·{r['c3']}·{r['c4']} 경보감소{r['body_alarm_loss']} 본체사건{r['body_incidents']} 시작{r['starts']} 격상{r['escalations']}"
for sid, r in data[vs[0]].items():
    line = f"{sid:10s} {r['desc'][:44]:44s} | {vs[0]}: {fmt(r)}"
    for v in vs[1:]:
        o = data[v].get(sid)
        if o and any(o[k] != r[k] for k in key):
            line += f" | {v}: {fmt(o)}"
        elif o:
            line += f" | {v}: 같음"
    if r.get("quality") is not None:
        q = r["quality"]; line += f" | 창 {[(a, (b or '열림')[11:23], (c or '열림')[11:23], d) for a, b, c, d in q]}"
        for v in vs[1:]:
            o = data[v].get(sid)
            if o and o.get("quality") != q:
                line += f" | {v} 창 {[(a, (b or '열림')[11:23], (c or '열림')[11:23], d) for a, b, c, d in o['quality']]}"
    print(line)
