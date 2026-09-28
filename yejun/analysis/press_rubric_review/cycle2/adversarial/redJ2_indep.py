# 독립 재구현(J2): 팀 코드를 import하지 않고 원본 CSV에서 v2 핵심 수치를 다시 계산
import numpy as np, pandas as pd, math
D="/Volumes/YJSSD/공모전/k-제조데이터/yejun/press_submission/data/3_소성가공_예지보전/"
S=["AI0_Vibration","AI1_Vibration","AI2_Current"]
def load(f):
    d=pd.read_csv(D+f); t=pd.to_datetime(d["TimeStamp"]); dt=t.diff().dt.total_seconds()
    new=(dt.sub(0.1).abs()>0.02).fillna(False).to_numpy(); new[0]=False
    d["seg"]=np.cumsum(new); d["pos"]=d.groupby("seg").cumcount()
    for c in S[:2]: d[c]=np.round(d[c]/1e-4)*1e-4
    d[S[2]]=np.round(d[S[2]]/1.1920929)*1.1920929
    return d
N=load("press_data_normal.csv"); A=load("outlier_data.csv")
FREQ=np.arange(0.0,5.0001,0.005)
def hats(w):
    t=np.arange(w)*0.1; H=[]
    for f in FREQ:
        X=np.column_stack([np.sin(2*np.pi*f*t),np.cos(2*np.pi*f*t),np.ones(w)])
        H.append(X@np.linalg.pinv(X))
    return H
HATS={6:hats(6),8:hats(8)}
def widx(seg,w):
    i=np.arange(w-1,len(seg)); return i[seg[i]==seg[i-w+1]]
def sine(x,seg,w):
    out=np.full(len(x),np.nan); idx=widx(seg,w)
    if not len(idx): return out
    W=np.stack([x[i-w+1:i+1] for i in idx]); sst=((W-W.mean(1,keepdims=True))**2).sum(1)
    best=np.full(len(idx),np.inf)
    for H in HATS[w]:
        r=W-W@H.T; best=np.minimum(best,(r*r).sum(1))
    v=np.where(sst>0,best/np.where(sst>0,sst,1),np.nan); out[idx]=np.clip(v,0,None); return out
class Tail:
    def __init__(s,ref):
        r=np.sort(ref[np.isfinite(ref)]); s.r=r; s.n=len(r); s.u=np.quantile(r,.95); e=r[r>s.u]-s.u; s.b=e.mean(); s.gu=s.emp(np.array([s.u]))[0]
    def emp(s,v): return -np.log10((s.n-np.searchsorted(s.r,v,side="left")+1)/(s.n+1))
    def __call__(s,v):
        v=np.asarray(v,float); o=np.full(v.shape,np.nan); ok=np.isfinite(v); x=v[ok]; res=np.empty_like(x); lo=x<=s.u
        res[lo]=s.emp(x[lo]); res[~lo]=s.gu+(x[~lo]-s.u)/(s.b*np.log(10)); o[ok]=res; return o
def arres(x,seg,c):
    o=np.full(len(x),np.nan); i=widx(seg,3); o[i]=np.abs(x[i]-c[0]-c[1]*x[i-1]-c[2]*x[i-2]); return o
def run(tr_end,cal_end,alpha=.01,drop=None):
    tr=N[N.seg<tr_end].reset_index(drop=True); ca=N[(N.seg>=tr_end)&(N.seg<cal_end)].reset_index(drop=True); te=N[N.seg>=cal_end].reset_index(drop=True)
    mu=tr[S].mean().to_numpy(); sd=tr[S].std(ddof=0).to_numpy()
    x=tr[S[2]].to_numpy(); sg=tr.seg.to_numpy(); i=widx(sg,3)
    c=np.linalg.lstsq(np.column_stack([np.ones(len(i)),x[i-1],x[i-2]]),x[i],rcond=None)[0]
    T=dict(m=Tail(np.abs((tr[S].to_numpy()-mu)/sd).max(1)),s6=Tail(sine(x,sg,6)),s8=Tail(sine(x,sg,8)),d=Tail(arres(x,sg,c)))
    def score(f):
        z=np.abs((f[S].to_numpy()-mu)/sd).max(1); cur=f[S[2]].to_numpy(); sg=f.seg.to_numpy(); pos=f.pos.to_numpy()
        gm=T["m"](z); gs=np.where(pos<7,T["s6"](sine(cur,sg,6)),T["s8"](sine(cur,sg,8))); gd=T["d"](arres(cur,sg,c))
        comps=dict(m=gm,s=gs,d=gd)
        if drop: comps[drop]=np.full(len(f),np.nan)
        return np.fmax(np.fmax(comps["m"],comps["s"]),comps["d"]),comps
    cs,_=score(ca); cal=pd.Series(np.where(np.isfinite(cs),cs,-np.inf)).groupby(ca.seg.to_numpy()).max().to_numpy()
    n=len(cal); a=math.floor(alpha*(n+1))-1; thr=np.sort(cal)[::-1][a]
    sn,_=score(te); sa,comps=score(A)
    an=np.isfinite(sn)&(sn>thr); aa=np.isfinite(sa)&(sa>thr)
    tp=int(aa.sum()); fn=int((~aa).sum()); fp=int(an.sum()); f1=2*tp/(2*tp+fp+fn)
    fa_seg=int(pd.Series(an).groupby(te.seg.to_numpy()).any().sum()); nseg=te.seg.nunique()
    det=pd.Series(aa).groupby(A.seg.to_numpy()).any(); 
    first=pd.DataFrame(dict(a=aa,p=A.pos.to_numpy(),s=A.seg.to_numpy())); fd=first[first.a].groupby("s").p.min()*0.1
    fn_pos01=int(((~aa)&(A.pos.to_numpy()<2)).sum())
    fa_list=sorted(te.seg[an].unique().tolist())
    return dict(n_cal=n,thr=round(float(thr),4),ar2=np.round(c,4).tolist(),tp=tp,fp=fp,fn=fn,f1=round(f1,6),fa_seg=f"{fa_seg}/{nseg}",fa_list=fa_list,det=f"{int(det.sum())}/{len(det)}",delay_max=float(fd.max()),fn_pos01=fn_pos01,rows_test=len(te))
for name,(a,b) in dict(A=(360,480),B=(300,420)).items():
    for al in (.01,.03,.05):
        print(name,al,run(a,b,al))
print("--- 성분 절제(α=1%) ---")
for name,(a,b) in dict(A=(360,480),B=(300,420)).items():
    for d,lab in (("s","파형 제거"),("d","예측오차 제거"),("m","크기 제거")):
        r=run(a,b,.01,drop=d); print(name,lab,{k:r[k] for k in ("tp","fp","fn","f1","fa_seg","det")})
