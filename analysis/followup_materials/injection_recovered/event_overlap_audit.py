"""Reproduce production-key overlap and defect-event scope from restored CSVs."""
from pathlib import Path
import json, zipfile
import numpy as np
import pandas as pd

HERE = Path(__file__).parent

def main():
    d = pd.read_csv(HERE/'labeled_unique_with_metadata.csv', keep_default_na=False)
    bad = d[d.y == 1].copy()
    key = ['EQUIP_CD', 'TimeStamp', 'PART_NAME']
    timekey = ['EQUIP_CD', 'TimeStamp']
    scope = {
        'all_unique_rows': len(d),
        'all_unique_shot_time_keys': len(d[timekey].drop_duplicates()),
        'bad_products': len(bad),
        'bad_calendar_days': bad.TimeStamp.str[:10].nunique(),
        'bad_plan_days': bad.PART_FACT_PLAN_DATE.nunique(),
        'bad_equipment': sorted(bad.EQUIP_CD.unique()),
        'bad_shot_time_keys': len(bad[timekey].drop_duplicates()),
        'bad_production_instruction_proxy_keys': len(bad[['EQUIP_CD','PART_FACT_PLAN_DATE','PART_FACT_SERIAL','PART_NAME']].drop_duplicates()),
        'bad_parts_by_time_multiplicity': bad.groupby(timekey).size().value_counts().to_dict(),
        'bad_day_details': [],
        'episodes_defined_by_gap_minutes': {},
        'interpretation': 'Timestamp and production-instruction keys are proxies, not verified independent physical failure incidents or cavity IDs.'
    }
    for date, g in bad.groupby(bad.TimeStamp.str[:10]):
        scope['bad_day_details'].append({'date': date, 'bad_products': len(g),
            'distinct_timestamp': g.TimeStamp.nunique(), 'first': g.TimeStamp.min(), 'last': g.TimeStamp.max(),
            'part_counts': g.PART_NAME.value_counts().to_dict(), 'reasons': g.Reason.value_counts().to_dict()})
    for gap in (3,5,10,30):
        clusters = 0
        for _, g in bad.groupby('EQUIP_CD'):
            ts = pd.to_datetime(g.TimeStamp.drop_duplicates()).sort_values()
            clusters += int((ts.diff().dt.total_seconds().fillna(float('inf')) > gap*60).sum())
        scope['episodes_defined_by_gap_minutes'][str(gap)] = clusters
    overlap = {}
    with zipfile.ZipFile(HERE/'contest_8077.zip') as z:
        for product in ('cn7','rg3'):
            member = next(n for n in z.namelist() if n.endswith(f'moldset_labeled_{product}.csv'))
            cols = pd.read_csv(z.open(member), nrows=0).columns
            features = [c for c in cols if c not in ('Unnamed: 0','PassOrFail')]
            a = pd.read_csv(HERE/f'contest_{product}_restored.csv', keep_default_na=False)
            b = pd.read_csv(HERE/f'contest_unlabeled_{product}_restored.csv', keep_default_na=False)
            b = b.merge(a[key], on=key, validate='many_to_one')
            joined = a.merge(b, on=key, suffixes=('_l','_u'), validate='one_to_one')
            diffs = np.abs(joined[[c+'_l' for c in features]].to_numpy()-joined[[c+'_u' for c in features]].to_numpy()).max(axis=1)
            overlap[product] = {'shared_equipment_timestamp_part_keys':len(joined),
                'unique_labeled_id':joined._id_l.nunique(),'unique_unlabeled_id':joined._id_u.nunique(),
                'sensor_max_difference_median':float(np.median(diffs)), 'sensor_max_difference_max':float(diffs.max()),
                'all_24_features_absdiff_under_0_0001_rows':int((diffs<.0001).sum()),
                'matching_key_bad_labels':int(joined.PassOrFail.sum())}
    for name, obj in [('defect_event_scope.json',scope),('labeled_unlabeled_overlap.json',overlap)]:
        (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda v:v.item()))

if __name__ == '__main__':
    main()
