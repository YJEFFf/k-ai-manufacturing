"""검토 10: review10_weak.py에서 a489001만 사건이 나뉜 위치(뒤바뀜 56·90, 2칸 늦음 40·73)의 행별 판정·사건 열을 찍는다. REVIEW_ENV=<사본 yejun> python review10_dbg_move.py"""
import sys, numpy as np, pandas as pd
import review7_weak as W, review10_weak as X
L,M,F,T=W.setup(0.1)
seg=L.D.segments(F); starts=np.flatnonzero(np.r_[True,seg[1:]!=seg[:-1]])
for pos,kind in [(56,'move1'),(90,'move1'),(40,'move2'),(73,'move2')]:
    near=[int(s) for s in starts if abs(s-pos)<60]
    f,err=X.make(L,F,T,kind,pos)
    p=M.predict(f); b=M.predict(F)
    print(kind,pos,'기록 시작 근처',near,'원자료 경보행',list(np.flatnonzero(b.alarm.to_numpy()[pos-15:pos+60])+pos-15)[:20])
    lo,hi=pos-3,pos+12
    print(p.iloc[lo:hi][['timestamp','status','record_id','alarm','incident_id','incident_notification','time_order_event']].to_string())
    print('사건 시작 행',list(np.flatnonzero(p.incident_notification.to_numpy())), '원자료',list(np.flatnonzero(b.incident_notification.to_numpy())))
