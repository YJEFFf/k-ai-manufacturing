"""Reproduce paired product/timestamp and exact-ratio evidence in recovered ID50."""
from pathlib import Path
import zipfile,json
import pandas as pd,numpy as np
path=next(Path('/tmp/kamp-followup-cache').glob('*정밀가공 품질보증*zip'))
with zipfile.ZipFile(path) as z:d=pd.read_csv(z.open('data/정밀가공_품질보증_데이터셋.csv'))
a=d[d.passorfail==1].set_index('SerialNo');n=d[d.passorfail==0].set_index('SerialNo').loc[a.index]
features=[c for c in d if c not in ['SerialNo','ReceivedDateTime','passorfail']]
changes={c:int((a[c]!=n[c]).sum()) for c in features}
ratios={c:(a[c]/n[c]).replace([np.inf,-np.inf],np.nan).dropna().round(8).value_counts().to_dict() for c in features if changes[c]}
r={'positive_rows':len(a),'same_timestamp':int((a.ReceivedDateTime==n.ReceivedDateTime).sum()),'changed_features_counts':changes,'ratios':ratios}
Path(__file__).with_name('id50_paired_augmentation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print('Verified',len(a),'pairs; unchanged timestamps:',r['same_timestamp'])
