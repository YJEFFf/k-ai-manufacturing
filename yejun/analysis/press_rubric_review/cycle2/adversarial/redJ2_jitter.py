# J2 독립 시험: 앨리어싱 가설(전류=교류 순시값, 원 주파수 k*10±0.6 Hz) 아래 표본화 시각 지터가 정상 기록의 경보율에 주는 영향
import numpy as np, pandas as pd, math
exec(open("redJ2_indep.py").read().split("for name,(a,b) in dict(A=(360,480)")[0])  # 함수·자료만 재사용
def build(tr_end,cal_end,alpha=.01):
    tr=N[N.seg<tr_end].reset_index(drop=True); ca=N[(N.seg>=tr_end)&(N.seg<cal_end)].reset_index(drop=True); te=N[N.seg>=cal_end].reset_index(drop=True)
    mu=tr[S].mean().to_numpy(); sd=tr[S].std(ddof=0).to_numpy()
    x=tr[S[2]].to_numpy(); sg=tr.seg.to_numpy(); i=widx(sg,3)
    c=np.linalg.lstsq(np.column_stack([np.ones(len(i)),x[i-1],x[i-2]]),x[i],rcond=None)[0]
    T=dict(m=Tail(np.abs((tr[S].to_numpy()-mu)/sd).max(1)),s6=Tail(sine(x,sg,6)),s8=Tail(sine(x,sg,8)),d=Tail(arres(x,sg,c)))
    def score(f):
        z=np.abs((f[S].to_numpy()-mu)/sd).max(1); cur=f[S[2]].to_numpy(); sg=f.seg.to_numpy(); pos=f.pos.to_numpy()
        gm=T["m"](z); gs=np.where(pos<7,T["s6"](sine(cur,sg,6)),T["s8"](sine(cur,sg,8))); gd=T["d"](arres(cur,sg,c))
        return np.fmax(np.fmax(gm,gs),gd),gm,gs,gd
    cs=score(ca)[0]; cal=pd.Series(np.where(np.isfinite(cs),cs,-np.inf)).groupby(ca.seg.to_numpy()).max().to_numpy()
    a=math.floor(alpha*(len(cal)+1))-1; thr=np.sort(cal)[::-1][a]
    return te,score,thr
def fit_rec(y):
    t=np.arange(len(y))*0.1; best=None
    for f in np.arange(0.55,0.651,0.002):
        X=np.c_[np.cos(2*np.pi*f*t),np.sin(2*np.pi*f*t),np.ones(len(y))]; b=np.linalg.lstsq(X,y,rcond=None)[0]; r=y-X@b
        sse=(r*r).sum()
        if best is None or sse<best[0]: best=(sse,f,b,r)
    return best
rng=np.random.default_rng(0)
for name,(a,b) in dict(A=(360,480),B=(300,420)).items():
    te,score,thr=build(a,b)
    recs=[g for _,g in te.groupby("seg") if len(g)>=17]
    base=None
    for fc in (60.6,):
        for jit_ms in (0,0.05,0.1,0.2,0.3,0.5,1.0,2.4):
            al=[];lv2=[];why={"m":0,"s":0,"d":0}
            for rep in range(5 if jit_ms>0 else 1):
                for g in recs:
                    y=g[S[2]].to_numpy(); sse,f,bb,r=fit_rec(y); t=np.arange(len(y))*0.1
                    dphi=2*np.pi*fc*rng.normal(0,jit_ms/1000,len(y)) if jit_ms>0 else 0
                    A_=np.hypot(bb[0],bb[1]); ph=np.arctan2(-bb[1],bb[0])   # y≈A cos(2πft+ph)+c
                    ynew=A_*np.cos(2*np.pi*f*t+ph+dphi)+bb[2]+r
                    h=g.copy(); h[S[2]]=np.round(ynew/1.1920929)*1.1920929
                    sc,gm,gs,gd=score(h); al_rows=np.isfinite(sc)&(sc>thr)
                    al.append(al_rows.any()); lv2.append(al_rows.sum()>=2)
                    if al_rows.any():
                        k=np.argmax(al_rows); 
                        comp=max((("m",gm[k]),("s",gs[k]),("d",gd[k])),key=lambda z:-np.inf if not np.isfinite(z[1]) else z[1])[0]; why[comp]+=1
            print(f"{name} fc={fc}Hz 지터σ={jit_ms:>4}ms: 1단계 경보 기록 {np.mean(al)*100:5.1f}%  2단계(경보≥2행) {np.mean(lv2)*100:5.1f}%  (기록 {len(recs)}개×반복) 첫경보 성분 {why}")
