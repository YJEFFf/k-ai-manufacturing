"""Read assigned KAMP archives in memory; never extract or modify originals.

Run with /tmp/kamp-review-venv/bin/python. JSON contains aggregate statistics,
not source rows. Passing --ids limits the audit to materialized archives.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import unicodedata
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = next(p for p in ROOT.iterdir() if unicodedata.normalize("NFC", p.name) == "데이터셋")
OUT = Path(__file__).with_name("energy_vision")
NAMES = {
    27: "Dataset_자원 최적화 AI 데이터셋.zip",
    41: "Dataset_표면처리 자원최적화 AI 데이터셋.zip",
    46: "Dataset_소성가공 자원최적화 AI 데이터셋.zip",
    26: "Dataset_공급망 최적화 AI 데이터셋.zip",
    30: "Dataset_생산계획 최적화 AI 데이터셋.zip",
    36: "Dataset_표면처리 공급망최적화 AI 데이터셋.zip",
    37: "Dataset_열처리 공급망최적화 AI 데이터셋.zip",
    12: "12. Dataset_XrayInspection.zip",
    25: "Dataset_품질 이상탐지 진단(크로메이트) AI 데이터셋.zip",
}


def path_for(seq):
    materialized = Path('/tmp/kamp-review-materialized') / NAMES[seq]
    if materialized.is_file() and materialized.stat().st_size:
        return materialized
    return next(p for p in DATA.iterdir() if unicodedata.normalize("NFC", p.name) == NAMES[seq])


def read_tables(z):
    tables = {}
    for info in z.infolist():
        if info.is_dir() or info.filename.startswith("__MACOSX/"):
            continue
        ext = Path(info.filename).suffix.lower()
        if ext not in {".csv", ".xls", ".xlsx"} or info.file_size > 60_000_000:
            continue
        raw = z.read(info)
        if ext == ".csv":
            for enc in ("utf-8-sig", "cp949", "utf-16"):
                try:
                    tables[info.filename] = pd.read_csv(io.BytesIO(raw), encoding=enc)
                    break
                except (UnicodeError, pd.errors.ParserError):
                    continue
        else:
            for sheet, df in pd.read_excel(io.BytesIO(raw), sheet_name=None).items():
                tables[f"{info.filename}:{sheet}"] = df
    return tables


def describe(df):
    result = {
        "shape": list(df.shape),
        "columns": [str(c) for c in df.columns],
        "missing_by_column": {str(k): int(v) for k, v in df.isna().sum().items()},
        "unique_by_column": {str(k): int(v) for k, v in df.nunique().items()},
        "duplicate_full_rows": int(df.duplicated().sum()),
        "numeric": df.select_dtypes(include="number").describe().to_dict() if len(df.select_dtypes(include="number").columns) else {},
    }
    dates = {}
    for c in df.columns:
        if any(k in str(c).lower() for k in ["date", "datetime", "날짜", "일자", "time_s", "시작", "종료"]):
            numeric = pd.api.types.is_numeric_dtype(df[c])
            if numeric and str(c) == '날짜' and df[c].dropna().between(19000101, 21001231).all():
                d = pd.to_datetime(df[c].astype('Int64').astype(str), errors='coerce', format='%Y%m%d')
            elif numeric and str(c) == 'Order_date' and df[c].dropna().between(40000, 50000).all():
                d = pd.to_datetime(df[c], errors='coerce', origin='1899-12-30', unit='D')
            elif numeric:
                continue  # Numeric date codes need an explicit format, never nanoseconds.
            else:
                d = pd.to_datetime(df[c], errors="coerce", format="mixed")
            if d.notna().mean() < .5:
                continue
            delta = d.dropna().sort_values().diff().dropna().dt.total_seconds()
            dates[str(c)] = {
                "min": str(d.min()), "max": str(d.max()), "days": int(d.dt.normalize().nunique()),
                "duplicates": int(d.duplicated().sum()), "nonmonotonic": not d.is_monotonic_increasing,
                "top_intervals_seconds": {str(k): int(v) for k, v in delta.value_counts().head(8).items()},
            }
    result["dates"] = dates
    return result


def audit(seq):
    p = path_for(seq)
    result = {"seq": seq, "file": p.name, "bytes": p.stat().st_size}
    if not p.stat().st_size:
        result["status"] = "empty archive; raw contents unavailable"
        return result
    with zipfile.ZipFile(p) as z:
        result["members"] = [dict(name=i.filename, bytes=i.file_size) for i in z.infolist()]
        result["crc_first_bad_member"] = z.testzip()
        result["tables"] = {n: describe(d) for n, d in read_tables(z).items()}
    result["status"] = "all archive bytes CRC-checked; tabular members parsed"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", type=int, default=list(NAMES))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for seq in args.ids:
        print(f"start {seq}", flush=True)
        try:
            result = audit(seq)
        except Exception as e:
            result = {"seq": seq, "error": repr(e)}
        (OUT / f"raw{seq}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print(f"done {seq}: {result.get('status', result.get('error'))}", flush=True)


if __name__ == "__main__":
    main()
