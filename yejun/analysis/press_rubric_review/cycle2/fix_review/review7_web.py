"""검토 7: 콘솔 모의 화면(app.js viewNow)의 튄 행 제외(부호 2·4)가 파이썬 cases()·incidents()와 같은가.
부호 4(기록 끝·기록 첫 행의 튐, 밀린 자료)가 여러 번 나오는 입력의 관측 접두부마다 Python(Console.analyze)과 app.js 집계를 대조한다.
사본의 test_web_prefix.cjs를 그대로 쓴다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_web.py
"""
import json
import shutil
import subprocess

from review7_lib import *  # noqa: F401,F403
from serve import Console  # noqa: E402

console = Console()
nt = normal_test("B")
pn = model("B").predict(nt)
rec = pn.record_id.to_numpy()
quiet = [r for r in np.unique(rec) if pn.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 30]
fa = [r for r in np.unique(rec) if pn.alarm[rec == r].sum() > 0]
abn, _ = base_abnormal()


def at(frame, start):
    out = D.inputs_only(frame).copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).strftime(FMT)
    return out


def shift(frame, i, seconds):
    out = frame.copy()
    out.loc[i, D.TIME] = (pd.Timestamp(out.loc[i, D.TIME]) + pd.Timedelta(seconds=seconds)).strftime(FMT)
    return out


t = pd.Timestamp("2022-07-12 00:00:00")
parts = []


def add(frame, gap=2.0):
    global t
    f = at(frame, t)
    parts.append(f)
    t = pd.Timestamp(f[D.TIME].iloc[-1]) + pd.Timedelta(seconds=gap)
    return f


add(nt[rec == quiet[0]])
a = add(abn.iloc[0:4]); b = add(abn.iloc[4:54])
parts[-1] = shift(parts[-1], len(b) - 1, 5)                       # 이상 기록 끝 행 +5초 → 다음 기록 앞 2행 보류·부호 4
add(abn.iloc[54:101])
c = add(nt[rec == quiet[1]])
parts[-1] = shift(parts[-1], 0, 4)                                # 정상 복귀 첫 행 +4초(기록 첫 행 튐, 부호 4)
add(nt[rec == quiet[2]])
d = add(abn.iloc[101:132])
parts[-1] = shift(parts[-1], 10, 5)                               # 기록 안 표본 대체 +5초(부호 2)
e = add(nt[rec == quiet[3]], gap=90)                             # 90초 중단
f = at(abn.iloc[132:150], t)
backlog = at(nt[rec == quiet[4]].iloc[:10], pd.Timestamp(e[D.TIME].iloc[-1]) + pd.Timedelta(seconds=30))
parts += [f.iloc[:1], backlog, f.iloc[1:]]                        # 중단 뒤 새 기록 첫 행 다음에 밀린 자료 10행(부호 4)
t = pd.Timestamp(f[D.TIME].iloc[-1]) + pd.Timedelta(seconds=2)
g = add(nt[rec == quiet[5]])
parts[-1] = shift(parts[-1], len(g) - 1, 3)                       # 경보 없는 기록 끝 +3초(부호 4)
nat = parts[-1].iloc[[0]].copy(); nat[D.TIME] = ""
h = add(abn.iloc[150:203])
parts.insert(len(parts) - 1, nat)                                 # 시각 결측 한 행을 보류 구간 앞에
add(nt[rec == quiet[6]])
frame = pd.concat(parts, ignore_index=True)


def analyze(data):
    return console.analyze(dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=data.to_csv(index=False)))


def compare(frame, label):
    full = analyze(frame)
    ev = [p["time_order_event"] for p in full["points"]]
    cut = set(range(0, len(frame), 9)) | {len(frame) - 1}
    for i, v in enumerate(ev):
        if v:
            cut.update(range(i - 3, i + 4))
    for cs in full["cases"]:
        cut.update((cs["first_row"] - 1, cs["first_row"], cs["row_to"], cs["row_to"] + 1))
    cut = sorted(x for x in cut if 0 <= x < len(frame))
    prefixes = []
    for cursor in cut:
        r = analyze(frame.iloc[:cursor + 1])
        prefixes.append(dict(cursor=cursor, cases=r["cases"], incidents=r["incidents"], alarm_rows=r["stats"]["alarm_rows"]))
    res = subprocess.run([shutil.which("node"), str(HERE / "test_web_prefix.cjs")], input=json.dumps(dict(full=full, prefixes=prefixes)),
                         text=True, encoding="utf-8", capture_output=True)
    print(f"{label}: 행 {len(frame)}, 시각 순서 부호 {pd.Series(ev).value_counts().sort_index().to_dict()}, 건 {len(full['cases'])}, "
          f"사건 {len(full['incidents'])}, 접두부 {len(prefixes)}곳 → node 종료 {res.returncode}: {(res.stdout + res.stderr).strip()[:400]}")
    for cs in full["cases"]:
        print(f"    건 {cs['case_uid']}: 사건 {cs['incident_id']} · 경보 {cs['alarm_rows']} · 창 {cs['suspect_from'][11:23] or '열림'} ~ {cs['suspect_to'][11:23] or '열림'}")
    return res.returncode


rc = compare(frame, "부호 4 여러 곳")
variant = frame.copy()
idx4 = [i for i, p in enumerate(analyze(frame)["points"]) if p["time_order_event"] == 4]
for i in idx4:                                                     # 부호 4 행 자체를 센서 결측으로
    variant.loc[i, D.SENSORS[0]] = np.nan
rc |= compare(variant, "부호 4 행이 센서 결측")
raise SystemExit(rc)
