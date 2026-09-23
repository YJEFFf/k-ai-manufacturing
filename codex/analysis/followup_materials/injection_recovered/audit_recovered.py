"""Audit newly hydrated ID4; never modify originals or infer cavity identities."""
from pathlib import Path
import collections, hashlib, json, zipfile
import numpy as np
import pandas as pd

HERE=Path(__file__).parent
SOURCE=Path('/tmp/kamp-followup-cache/04. Dataset_Molding.zip')

def scalar(x):
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

def frame_info(d):
    return {'rows':len(d),'columns':list(d.columns),'missing':{k:int(v) for k,v in d.isna().sum().items()},
      'full_duplicates':int(d.duplicated().sum()),'column_unique':{k:int(v) for k,v in d.nunique(dropna=False).items()}}

def main():
    result={}
    with zipfile.ZipFile(SOURCE) as z:
        result['zip_crc_first_bad']=z.testzip()
        result['members']=[{'name':i.filename,'bytes':i.file_size,'compressed':i.compress_size} for i in z.infolist()]
        raw=pd.read_csv(z.open('dataset/labeled_data.csv'),keep_default_na=False)
        raw['y']=raw.PassOrFail.map({'Y':0,'N':1})
        result['raw_labeled']=frame_info(raw)
        result['raw_labeled']['labels']=raw.PassOrFail.value_counts().to_dict()
        result['raw_labeled']['id_multiplicity']=raw.groupby('_id').size().value_counts().to_dict()
        result['raw_labeled']['id_label_conflicts']=int((raw.groupby('_id').y.nunique()>1).sum())
        unique=raw.drop_duplicates().copy();unique['date']=unique.TimeStamp.str[:10]
        result['unique_labeled']=frame_info(unique)
        result['unique_labeled']['labels']=unique.PassOrFail.value_counts().to_dict()
        result['unique_labeled']['date_product']=unique.groupby(['date','PART_NAME']).agg(n=('y','size'),bad=('y','sum')).reset_index().to_dict('records')
        result['unique_labeled']['defect_reasons']=unique[unique.y==1].groupby(['date','Reason']).size().reset_index(name='n').to_dict('records')
        result['unique_labeled']['timestamp_range']=[unique.TimeStamp.min(),unique.TimeStamp.max()]
        result['unique_labeled']['plan_date_count']=unique.PART_FACT_PLAN_DATE.nunique()
        unique.to_csv(HERE/'labeled_unique_with_metadata.csv',index=False)
        first=pd.read_csv(z.open('dataset/moldset_labeled.csv'),keep_default_na=False).set_index('Unnamed: 0')
        result['first_processed_labeled']=frame_info(first)
        joined=first.merge(unique[['_id','PassOrFail','Reason']],on='_id',suffixes=('_processed','_raw'),validate='one_to_one')
        result['target_mapping_mismatches']=int((joined.PassOrFail_processed!=joined.PassOrFail_raw.map({'Y':0,'N':1})).sum())
        result['reason_mapping_mismatches']=int((joined.Reason_processed!=joined.Reason_raw).sum())
        mappings=[];wanted_unlabeled=set();features=None
        for kind in ('labeled','unlabeled'):
            for prod in ('cn7','rg3'):
                name=f'moldset_{kind}_{prod}.csv';d=pd.read_csv(z.open('dataset/'+name));indices=d['Unnamed: 0'].to_numpy()
                feat=[c for c in d if c not in ('Unnamed: 0','PassOrFail')];features=feat
                rr={'name':name,'rows':len(d),'sha256':hashlib.sha256(z.read('dataset/'+name)).hexdigest(),'first_index':int(indices.min()),'last_index':int(indices.max())}
                if kind=='labeled':
                    restored=first.loc[indices].copy();restored['contest_row']=indices
                    x=restored[feat];std=x.std(ddof=0).replace(0,1)
                    err=np.abs((x-x.mean())/std-d[feat].to_numpy()).to_numpy()
                    rr.update(target_mismatch=int((restored.PassOrFail.to_numpy()!=d.PassOrFail.to_numpy()).sum()),
                        max_standardization_error=float(err.max()),dates=restored.TimeStamp.str[:10].value_counts().to_dict(),
                        product_labels=restored.groupby(['PART_NAME','PassOrFail']).size().reset_index(name='n').to_dict('records'))
                    hs=pd.util.hash_pandas_object(d[feat],index=False)
                    c=d.assign(group=hs.to_numpy()).groupby('group').PassOrFail.nunique()
                    conflicts=set(c[c>1].index)
                    restored['sensor_group']=hs.to_numpy();conf=restored[restored.sensor_group.isin(conflicts)]
                    rr['conflicting_sensor_groups']=len(conflicts)
                    rr['conflicts_after_restoring_part_name']=int((conf.groupby(['sensor_group','PART_NAME']).PassOrFail.nunique()>1).sum())
                    rr['all_conflict_pairs_same_timestamp']=bool((conf.groupby('sensor_group').TimeStamp.nunique()==1).all())
                    rr['all_conflict_pairs_different_part_name']=bool((conf.groupby('sensor_group').PART_NAME.nunique()==2).all())
                    rr['conflict_examples']=conf[['_id','TimeStamp','PART_NAME','PART_FACT_SERIAL','PassOrFail','Reason','contest_row']].head(8).to_dict('records')
                    restored.to_csv(HERE/f'contest_{prod}_restored.csv',index=False)
                else:wanted_unlabeled.update(indices.tolist())
                mappings.append(rr)
        result['contest_restoration']=mappings
        # Keep only the exact unlabelled contest row indices in memory; scan every input row.
        keep=[];total=0;dates=collections.Counter();products=collections.Counter();badcounts=[];missing=collections.Counter()
        for chunk in pd.read_csv(z.open('dataset/unlabeled_data.csv'),keep_default_na=False,chunksize=50000):
            total+=len(chunk);dates.update(chunk.TimeStamp.str[:10]);products.update(chunk.PART_NAME)
            missing.update({c:int(v) for c,v in chunk.isna().sum().items()})
            keep.append(chunk[chunk['Unnamed: 0'].isin(wanted_unlabeled)])
        selected=pd.concat(keep).set_index('Unnamed: 0')
        result['unlabeled_full']={'rows':total,'date_count':len(dates),'date_min':min(dates),'date_max':max(dates),'product_count':len(products),'selected_rows':len(selected)}
        result['unlabeled_restoration']=[]
        for prod in ('cn7','rg3'):
            d=pd.read_csv(z.open(f'dataset/moldset_unlabeled_{prod}.csv'));r=selected.loc[d['Unnamed: 0']]
            x=r[features];std=x.std(ddof=0).replace(0,1);err=np.abs((x-x.mean())/std-d[features].to_numpy()).to_numpy()
            rr={'product':prod,'rows':len(r),'max_standardization_error':float(err.max()),'date_count':r.TimeStamp.str[:10].nunique(),'date_min':r.TimeStamp.min(),'date_max':r.TimeStamp.max(),
                'daily_defect_count_column_present':'ERR_FACT_QTY' in r,'error_count_values':r.ERR_FACT_QTY.value_counts().to_dict(),
                'distinct_id_overlap_labeled':len(set(r._id)&set(unique._id))}
            result['unlabeled_restoration'].append(rr)
            r.to_csv(HERE/f'contest_unlabeled_{prod}_restored.csv')
    contest=HERE/'contest_8077.zip'
    if contest.exists():
        with zipfile.ZipFile(contest) as a,zipfile.ZipFile(SOURCE) as b:
            result['contest_exact_byte_match']={Path(n).name:a.read(n)==b.read('dataset/'+Path(n).name) for n in a.namelist() if n.endswith('.csv')}
    (HERE/'recovered_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=scalar))
    print(json.dumps({k:v for k,v in result.items() if k not in ('raw_labeled','unique_labeled','first_processed_labeled')},ensure_ascii=False,indent=2,default=scalar),flush=True)

if __name__=='__main__':main()
