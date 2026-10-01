"""참고 점검: 같은 수행기관(㈜인터엑스)의 KAMP 「용접 예지보전 AI 데이터셋」에서도 정상/이상 파일의 생성 형식이 다른지 본다.

외부(다른 KAMP) 데이터이므로 학습·평가에는 쓰지 않는다. zip을 풀지 않고 읽기만 한다.
실행: python pilot_weld_format.py --zip "<데이터셋/Dataset 용접 예지보전 AI 데이터셋.zip>"
"""
import argparse, csv, io, zipfile, collections
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('--zip', required=True); a = ap.parse_args()
with zipfile.ZipFile(a.zip) as z:
    for name in ['data/normal_data.csv', 'data/outlier_data.csv']:
        rows = list(csv.reader(io.TextIOWrapper(z.open(name), encoding='utf-8-sig')))
        hdr, body = rows[0], rows[1:]
        print(f'== {name}: {len(body)} rows, header={hdr}')
        for k, c in enumerate(hdr):
            if c in ('DV_R', 'DA_R', 'AV_R', 'AA_R', 'PM_R', 'FIN_JGMT'):
                v = np.array([float(r[k]) for r in body])
                u = np.unique(v); d = np.diff(u)
                print(f'  {c}: unique {len(u)}, min spacing {d.min() if len(d) else None}, examples {u[:6].tolist()}')
