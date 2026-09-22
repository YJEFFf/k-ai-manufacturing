"""Reconstruct index/timestamp implications of guide48, not its neural model."""
from pathlib import Path
import zipfile,json
import numpy as np,pandas as pd
P=next(Path('/tmp/kamp-followup-cache').glob('*소성가공 예지*zip'));out={}
with zipfile.ZipFile(P) as z:
 for n in z.namelist():
  if not n.endswith('.csv'):continue
  d=pd.read_csv(z.open(n));t=pd.to_datetime(d.TimeStamp);r={};out[n]=r
  for label,a in [('full',d),('guide_evaluation_pool',d.iloc[15000:] if len(d)>600 else d)]:
   tt=pd.to_datetime(a.TimeStamp).reset_index(drop=True);y=a.Equipment_state.to_numpy();idx=np.arange(len(a)-120)
   horizon=(tt.iloc[idx+120].to_numpy()-tt.iloc[idx+19].to_numpy())/np.timedelta64(1,'s')
   length=(tt.iloc[idx+19].to_numpy()-tt.iloc[idx].to_numpy())/np.timedelta64(1,'s')
   r[label]={'rows':len(a),'windows':len(idx),'input20_elapsed_seconds_quantiles':{str(q):float(np.quantile(length,q)) for q in [0,.5,.9,1]},'input_end_to_label_elapsed_seconds_quantiles':{str(q):float(np.quantile(horizon,q)) for q in [0,.5,.9,1]},'input_end_to_label_exact_10_seconds':int((horizon==10).sum()),'input_first_state_same_as_future_label':int((y[idx]==y[idx+120]).sum())}
  split=300 if len(d)==600 else 880
  r['guide_validation_test_boundary']={'validation_windows':split,'last_validation_start':split-1,'first_test_start':split,'shared_input_rows':len(set(range(split-1,split-1+20))&set(range(split,split+20))),'note':'Class-specific pool-relative indices; neighbors share 19 of 20 input rows.'}
out['guide_reported_metrics']={'tn':3922,'fp':78,'tp':154,'fn':26,'precision':154/232,'recall':154/180,'f1':308/(308+78+26),'fpr':78/4000,'note':'Guide PDF40-41; not an independently rerun neural-model score.'}
Path(__file__).with_suffix('.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
