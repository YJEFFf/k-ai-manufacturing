"""과제 쏠림(같은 과제 강팀 수에 따른 차별성 감점)과 결선 과제 안배를 넣은 서면평가 모의실험."""
import numpy as np

rng = np.random.default_rng(20260926)
TASKS = {"power": 35, "injection": 22, "xray": 15, "welding": 15, "press": 13}  # 100팀 가정

def draw_quality(n, ex=0.03, gd=0.12):
    u = rng.random(n)
    q = np.where(u < ex, rng.normal(88, 4, n), np.where(u < ex + gd, rng.normal(78, 5, n), rng.normal(62, 10, n)))
    strong = u < ex + gd
    return np.clip(q, 0, 100), strong

def one(my_task, my_mu, my_sd, crowd=0.5, cap=3.0, quota=None, ex=0.03, gd=0.12, scale=1.0):
    tasks, qual, strong = [], [], []
    for t, n in TASKS.items():
        n = int(round(n * scale))
        k = n - 1 if t == my_task else n
        q, s = draw_quality(k, ex, gd)
        tasks += [t] * k
        qual += list(q)
        strong += list(s)
    # 우리 팀(강팀으로 간주)
    tasks.append(my_task)
    qual.append(float(np.clip(rng.normal(my_mu, my_sd), 0, 100)))
    strong.append(True)
    tasks = np.array(tasks)
    qual = np.array(qual)
    strong = np.array(strong)
    # 과제 쏠림: 같은 과제의 다른 강팀 수 × crowd 점 감점(최대 cap)
    n_strong = {t: strong[tasks == t].sum() for t in TASKS}
    pen = np.array([min(cap, crowd * (n_strong[t] - (1 if s else 0))) for t, s in zip(tasks, strong)])
    true = qual - pen
    judged = true[:, None] + rng.normal(0, 5, (len(true), 5))
    judged.sort(axis=1)
    sc = judged[:, 1:4].mean(axis=1)
    me = len(sc) - 1
    order = np.argsort(-sc)
    if quota is None:
        finalists = order[:8]
    else:
        cnt, finalists = {}, []
        for i in order:
            if cnt.get(tasks[i], 0) < quota:
                finalists.append(i)
                cnt[tasks[i]] = cnt.get(tasks[i], 0) + 1
            if len(finalists) == 8:
                break
    rank = 1 + (sc > sc[me]).sum()
    return me in finalists, rank <= 3, rank == 1

def run(my_task, mu, sd, reps=6000, **kw):
    r = np.array([one(my_task, mu, sd, **kw) for _ in range(reps)])
    return r.mean(axis=0)

teams = {"전력 고점": ("power", 92.5, 2), "프레스 고점(현 계획)": ("press", 89.5, 2),
         "프레스 고점(한계 보완 후)": ("press", 91.5, 2), "프레스 고점(보완 하향 90.5)": ("press", 90.5, 2),
         "전력 현재": ("power", 88, 3), "프레스 현재": ("press", 85, 3)}
settings = {
    "쏠림 없음·순수 점수": dict(crowd=0.0, quota=None),
    "쏠림 감점·순수 점수": dict(crowd=0.5, quota=None),
    "쏠림 감점·과제당 최대 3팀": dict(crowd=0.5, quota=3),
    "쏠림 감점·과제당 최대 2팀": dict(crowd=0.5, quota=2),
    "쏠림 강함(1점/팀, 최대 4)·과제당 최대 2팀": dict(crowd=1.0, cap=4.0, quota=2),
}
for sname, kw in settings.items():
    print("==", sname)
    for name, (t, mu, sd) in teams.items():
        top8, top3, top1 = run(t, mu, sd, **kw)
        print(f"  {name:22s} 결선(상위8) {top8:.2f}  점수 상위3 {top3:.2f}  1위 {top1:.2f}")
