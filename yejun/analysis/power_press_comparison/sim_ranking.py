"""서면평가 순위 모의실험: 가정이 결과를 어떻게 바꾸는지 보기 위한 계산(예측값이 아니라 가정의 함의)."""
import numpy as np

rng = np.random.default_rng(20260926)

def pool(n, excellent_share, good_share):
    """경쟁 팀의 '실제 품질' 점수(100점): 대다수 보통, 일부 우수, 극소수 최상위."""
    k_ex = rng.binomial(n, excellent_share)
    k_gd = rng.binomial(n - k_ex, good_share / (1 - excellent_share))
    k_ty = n - k_ex - k_gd
    s = np.r_[rng.normal(62, 10, k_ty), rng.normal(78, 5, k_gd), rng.normal(88, 4, k_ex)]
    return np.clip(s, 0, 100)

def judged(true):
    """심사위원 5명: 각자 잡음(표준편차 5), 최고·최저 하나씩 빼고 평균."""
    j = true[:, None] + rng.normal(0, 5, (len(true), 5))
    j.sort(axis=1)
    return j[:, 1:4].mean(axis=1)

def run(ours_mu, ours_sd, n=100, ex=0.03, gd=0.12, reps=20000):
    ranks = np.empty(reps, int)
    for r in range(reps):
        comp = pool(n - 1, ex, gd)
        me = np.clip(rng.normal(ours_mu, ours_sd), 0, 100)
        sc = judged(np.r_[me, comp])
        ranks[r] = 1 + (sc[1:] > sc[0]).sum()
    return dict(top8=np.mean(ranks <= 8), top3=np.mean(ranks <= 3), top1=np.mean(ranks == 1),
                median_rank=float(np.median(ranks)))

scen = {
    "전력 현재(보고서가 현 작업 반영)": (88, 3),
    "프레스 현재": (85, 3),
    "전력 현실적 고점": (92.5, 2),
    "프레스 현실적 고점": (89.5, 2),
}
pools = {"기본(100팀, 최상위 3%·우수 12%)": dict(n=100, ex=0.03, gd=0.12),
         "강한 풀(150팀, 최상위 6%·우수 15%)": dict(n=150, ex=0.06, gd=0.15),
         "약한 풀(60팀, 최상위 2%·우수 10%)": dict(n=60, ex=0.02, gd=0.10)}
for pname, pk in pools.items():
    print("==", pname)
    for name, (mu, sd) in scen.items():
        r = run(mu, sd, reps=8000, **pk)
        print(f"  {name:28s} 상위8 {r['top8']:.2f} 상위3 {r['top3']:.2f} 1위 {r['top1']:.2f} 중앙순위 {r['median_rank']:.0f}")
