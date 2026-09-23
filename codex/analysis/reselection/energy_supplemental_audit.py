"""Additional key/date checks for KAMP 26 and 30; never modify raw files."""
from pathlib import Path
import json
import zipfile
import pandas as pd
from energy_vision_audit import path_for, read_tables

res = {}
with zipfile.ZipFile(path_for(26)) as z:
    d = next(iter(read_tables(z).values()))
ts = pd.to_datetime(d['CRET_TIME'].astype(str), format='%Y%m%d%H%M', errors='coerce')
dp = d.assign(timestamp=ts).groupby('Part Number')['timestamp'].agg(['count', 'nunique', 'min', 'max'])
g = d.assign(ts=ts).groupby(['Part Number', ts.dt.date]).last()
res['26'] = {
    'rows': len(d), 'parts': int(d['Part Number'].nunique()),
    'timestamps': int(ts.nunique()), 'days': int(ts.dt.normalize().nunique()),
    'start': str(ts.min()), 'end': str(ts.max()), 'parse_failure': int(ts.isna().sum()),
    'duplicate_part_timestamp': int(d.assign(ts=ts).duplicated(['Part Number', 'ts']).sum()),
    'rows_per_part_range': [int(dp['count'].min()), int(dp['count'].max())],
    'daily_rows_per_part_range': [int(g.groupby(level=0).size().min()), int(g.groupby(level=0).size().max())],
    'notes': 'Recorded future quantity columns are contemporaneous plans, not realized future orders.',
}
with zipfile.ZipFile(path_for(30)) as z:
    tables = read_tables(z)
m = tables['data/machine_info.csv']
o = tables['data/order_info.csv']
ts = pd.to_datetime(o['영업납기'], errors='coerce')
res['30'] = {
    'machine_rows': len(m), 'machine_unique': int(m['machine'].nunique()),
    'items': int(m['item'].nunique()),
    'duplicate_item_machine_keys': int(m.duplicated(['item', 'machine']).sum()),
    'machine_nulls': m.isna().sum().to_dict(), 'order_rows': len(o),
    'order_dates': [str(ts.min()), str(ts.max())], 'order_date_unique': int(ts.nunique()),
    'order_item_unique': int(o['중산도면'].nunique()),
    'order_classification_present': int(o['선급'].notna().sum()),
    'order_classification_missing': int(o['선급'].isna().sum()),
    'orders_without_machine_item': int((~o['중산도면'].isin(m['item'])).sum()),
    'notes': 'No energy measurement column; original workbook includes title/header rows and processed version is not independent sample.',
}
Path(__file__).with_name('energy_vision').joinpath('supplemental26_30_check.json').write_text(
    json.dumps(res, ensure_ascii=False, indent=2, default=str)
)
print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
