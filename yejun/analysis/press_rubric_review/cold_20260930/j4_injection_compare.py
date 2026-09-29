"""J4 위원 독립 점검 6: 인공 고장 주입에서 v2(J4 재구현)와 3-모수 단순 규칙(J4 재구현)을 같은 보정 규칙으로 비교한다.

팀 코드를 쓰지 않는다. 팀 E1(press_supplement/README.md 11~38행)을 문장 정의대로 근사한다. 세부(σ·진폭 정의)는 J4 가정이다.
- 대상: 각 분할 정상 평가 기록 중 30행 이상. 10행째(1초)부터 계단형 주입, 탐지 = 위치 10~29(2초) 안에 α=1% 경보.
- σ·μ: 정상 학습 행의 센서별 SD(ddof=0)·평균(matched 후). 팀 E1(common.py inject)과 같은 정의로 맞췄다.
- 족: 전류 잡음 s·σ(가우스, 반복 5), 전류 오프셋 d·√2·σ_전류, 진동 잡음 s·σ(두 진동, 반복 5), 전류 배율 k(학습 평균 μ 둘레로 확대).
목적: v2의 '약한 고장 민감도' 우위가 단순 규칙 대비로도 있는지 본다. v2 J4 재현값을 팀 E1과 대조해 근사의 타당성을 먼저 확인한다.
실행: python j4_injection_compare.py <원본 데이터 폴더>   결과: j4_injection_compare.json
"""
import json
import sys
from pathlib import Path

src = Path(__file__).with_name("j4_independent_v2.py").read_text(encoding="utf-8")
ns = {"__name__": "j4_defs"}
exec(compile(src.split("seg_n, seg_a = records(normal), records(abnormal)")[0], "j4_defs", "exec"), ns)
np, pd = ns["np"], ns["pd"]
normal, abnormal, records, positions, matched, J4Guard, S = (ns[k] for k in ("normal", "abnormal", "records", "positions", "matched", "J4Guard", "S"))
seg_n = records(normal)
pos_n = positions(seg_n)
PHI1 = 2 * np.cos(2 * np.pi * 0.6 * 0.1)


def simple_parts(df, seg):
    X = matched(df)
    x = X[S[2]].to_numpy()
    r = np.full(len(x), np.nan)
    i = np.arange(2, len(x))
    i = i[seg[i] == seg[i - 2]]
    r[i] = np.abs(x[i] - PHI1 * x[i - 1] + x[i - 2])
    return np.column_stack([np.abs(X[S[0]].to_numpy()), np.abs(X[S[1]].to_numpy()), r])


def pfun(ref):
    ref = np.sort(ref)

    def p(v):
        out = np.full(len(v), np.nan)
        ok = np.isfinite(v)
        out[ok] = (len(ref) - np.searchsorted(ref, v[ok], side="left") + 1) / (len(ref) + 1)
        return out
    return p


FAMILIES = [("none", 0, 1)] + [("cur_noise", s, 5) for s in (0.05, 0.1, 0.2)] + [("cur_offset", d, 1) for d in (0.2, 0.4, 0.8)] + \
           [("vib_noise", s, 5) for s in (1, 2, 4)] + [("cur_scale", k, 1) for k in (1.15, 1.5)]
res = {}
for split, (tr_end, cal_end) in {"A": (360, 480), "B": (300, 420)}.items():
    tr, cal, te = seg_n < tr_end, (seg_n >= tr_end) & (seg_n < cal_end), seg_n >= cal_end
    g = J4Guard(normal[tr].reset_index(drop=True), seg_n[tr])
    sc = g.score(normal[cal].reset_index(drop=True), seg_n[cal])
    p_v2 = pfun(pd.Series(np.where(np.isfinite(sc), sc, -np.inf)).groupby(seg_n[cal]).max().to_numpy())
    P_tr = simple_parts(normal[tr].reset_index(drop=True), seg_n[tr])
    scale = np.nanmax(P_tr, axis=0)
    s_cal = np.nanmax(simple_parts(normal[cal].reset_index(drop=True), seg_n[cal]) / scale, axis=1)
    p_sr = pfun(pd.Series(s_cal).groupby(seg_n[cal]).max().to_numpy())
    sigma = matched(normal[tr]).std(ddof=0).to_numpy()
    mu = matched(normal[tr]).mean().to_numpy()
    base = normal[te].reset_index(drop=True)
    sg, ps = seg_n[te], pos_n[te]
    lens = pd.Series(sg).groupby(sg).transform("size").to_numpy()
    elig = lens >= 30
    rec_ids = np.unique(sg[elig])
    inj_rows = elig & (ps >= 10)
    win = elig & (ps >= 10) & (ps < 30)
    cur = base[S[2]].to_numpy(float)
    pre = pd.DataFrame(dict(s=sg, p=ps, c=cur))[elig & (ps < 10)]
    amp = pre.groupby("s").c.apply(lambda v: np.sqrt(2) * np.sqrt(np.mean((v - v.mean()) ** 2)))
    mean10 = pre.groupby("s").c.mean()
    out = {}
    for fam, level, reps in FAMILIES:
        det_v2, det_sr = [], []
        for rep in range(reps):
            rng = np.random.default_rng(rep)
            df = base.copy()
            if fam == "cur_noise":
                df.loc[inj_rows, S[2]] = df.loc[inj_rows, S[2]] + rng.normal(0, level * sigma[2], inj_rows.sum())
            elif fam == "cur_offset":
                df.loc[inj_rows, S[2]] = df.loc[inj_rows, S[2]] + level * np.sqrt(2) * sigma[2]
            elif fam == "vib_noise":
                for k in (0, 1):
                    df.loc[inj_rows, S[k]] = df.loc[inj_rows, S[k]] + rng.normal(0, level * sigma[k], inj_rows.sum())
            elif fam == "cur_scale":
                df.loc[inj_rows, S[2]] = mu[2] + level * (df.loc[inj_rows, S[2]].to_numpy() - mu[2])
            a_v2 = p_v2(g.score(df, sg)) <= 0.01
            a_sr = p_sr(np.nanmax(simple_parts(df, sg) / scale, axis=1)) <= 0.01
            det_v2.append(pd.Series(a_v2 & win).groupby(sg).any().reindex(rec_ids).mean())
            det_sr.append(pd.Series(a_sr & win).groupby(sg).any().reindex(rec_ids).mean())
        out[f"{fam}_{level}"] = dict(v2=round(100 * float(np.mean(det_v2)), 1), simple_rule=round(100 * float(np.mean(det_sr)), 1))
    res[split] = dict(eligible_records=int(len(rec_ids)), detection_within_2s_pct=out)
Path(__file__).with_name("j4_injection_compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
