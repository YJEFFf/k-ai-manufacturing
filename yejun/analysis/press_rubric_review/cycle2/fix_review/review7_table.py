"""검토 7: 상황표 jsonl 세 개를 보고서용 마크다운 표로 만든다(c7d8bba 결과, 앞 판과 다른 칸만 괄호로)."""
import json, sys
paths = dict(arg.split("=", 1) for arg in sys.argv[1:])
data = {v: {r["sid"]: r for r in map(json.loads, open(p))} for v, p in paths.items()}
vs = list(paths)
cols = [("held", "보류"), ("c2", "부호2"), ("c4", "부호4"), ("c3", "부호3"), ("body_alarm_loss", "경보 감소"), ("body_incidents", "본체 사건"), ("starts", "시작"), ("escalations", "격상")]
print("| ID | 상황 | " + " | ".join(n for _, n in cols) + " | 앞 판과 다른 점 |")
print("|---|---|" + "---|" * (len(cols) + 1))
for sid, r in data[vs[0]].items():
    diffs = []
    for v in vs[1:]:
        o = data[v].get(sid)
        if o is None:
            continue
        d = [f"{n} {o[k]}" for k, n in cols if o[k] != r[k]]
        if r.get("quality") is not None and o.get("quality") != r.get("quality"):
            d.append("품질 창 다름")
        if d:
            diffs.append(f"{v}: " + "·".join(d))
    q = ""
    if r.get("quality"):
        q = " / 창 " + ", ".join(f"{(b or '열림')[11:23]}~{(c or '열림')[11:23]}" for _, b, c, _o in r["quality"])
    print(f"| {sid} | {r['desc']}{q} | " + " | ".join(str(r[k]) for k, _ in cols) + f" | {'; '.join(diffs) or '같음'} |")
