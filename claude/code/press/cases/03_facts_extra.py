"""보고서 1.6절 데이터 결함 진단표의 보조 수치를 파일로 남긴다(report/facts.csv의 근거).

입력: data/3_소성가공_예지보전/ 두 CSV (정밀도 맞춤본과 원본 문자열 둘 다)
출력: outputs/facts_extra.json (측정 비율·기록 구조·전류 수준·진동 상관·형식 누수)
실행: python code/press/cases/03_facts_extra.py
"""
import json

import numpy as np
import pandas as pd

from common import DATA, OUT, load_both


def main():
    normal, abnormal = load_both()
    raw_n = pd.read_csv(DATA / "press_data_normal.csv")
    out = {}
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        ts = pd.to_datetime(d.TimeStamp)
        span = (ts.max() - ts.min()).total_seconds()
        by_rec = d.groupby("rec")
        lens = by_rec.size()
        means = by_rec.AI2_Current.mean()
        long = by_rec.filter(lambda g: len(g) >= 20)  # 상관·SD 비는 20행 이상 기록에서만 잰다
        corr = long.groupby("rec").apply(lambda g: np.corrcoef(g.AI0_Vibration, g.AI1_Vibration)[0, 1], include_groups=False)
        ratio = long.groupby("rec").apply(lambda g: g.AI0_Vibration.std() / g.AI1_Vibration.std(), include_groups=False)
        ge10 = by_rec.filter(lambda g: len(g) >= 10).groupby("rec").AI2_Current
        offset = (ge10.mean().abs() > ge10.std())  # 평균 절댓값이 SD보다 큰 기록(0 근처를 오가지 않는 기록)
        # measured_share = 행 수 × 0.1초 / 전체 시간. 수집이 띄엄띄엄이라 1보다 한참 작다
        out[name] = dict(
            rows=int(len(d)), start=str(ts.min()), end=str(ts.max()), weekday=ts.min().day_name(),
            span_s=round(span, 1), measured_s=round(len(d) * 0.1, 1), measured_share=round(len(d) * 0.1 / span, 4),
            records=int(lens.size), records_exactly_50=int((lens == 50).sum()), records_over_50=int((lens > 50).sum()),
            records_under_8=int((lens < 8).sum()), records_under_10=int((lens < 10).sum()),
            record_current_mean_min=round(float(means.min()), 1), record_current_mean_max=round(float(means.max()), 1),
            records_ge10=int(offset.size), records_ge10_abs_mean_gt_sd=int(offset.sum()),
            current_mean=round(float(d.AI2_Current.mean()), 1), current_negative_share=round(float((d.AI2_Current < 0).mean()), 3),
            vib_upper_sd=round(float(d.AI0_Vibration.std()), 3), vib_lower_sd=round(float(d.AI1_Vibration.std()), 3),
            records_ge20=int(corr.size), upper_lower_corr_median=round(float(corr.median()), 2),
            upper_lower_corr_negative_share=round(float((corr < 0).mean()), 2),
            upper_over_lower_sd_median=round(float(ratio.median()), 2))
    # JSON 키 순서를 지키려고 아래 두 값은 반복문 밖에서 붙인다
    out["normal"]["duplicate_rows"] = int(raw_n.duplicated(subset=["TimeStamp", "AI0_Vibration", "AI1_Vibration", "AI2_Current"]).sum())
    # 형식 누수: 원본(문자열 그대로)과 정밀도 맞춤 후에 같은 '자릿수 > 6' 규칙을 적용해 비교한다
    raw_a = pd.read_csv(DATA / "outlier_data.csv", dtype={"AI0_Vibration": str})
    raw_n2 = pd.read_csv(DATA / "press_data_normal.csv", dtype={"AI0_Vibration": str})
    digits = lambda s: s.str.split(".").str[1].fillna("").str.len()  # 소수점 아래 자릿수
    leak = {}
    for tag, vn, va in (("raw", digits(raw_n2.AI0_Vibration), digits(raw_a.AI0_Vibration)),
                        ("matched", digits(normal.AI0_Vibration.map(lambda v: repr(round(v, 4)))), digits(abnormal.AI0_Vibration.map(lambda v: repr(round(v, 4)))))):
        pred = np.r_[(vn > 6).to_numpy(), (va > 6).to_numpy()]
        y = np.r_[np.zeros(len(vn)), np.ones(len(va))].astype(bool)
        tp, fp, fn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum())
        leak[tag] = dict(f1=round(2 * tp / (2 * tp + fp + fn), 3) if tp else 0.0, tp=tp, fp=fp, fn=fn,
                         normal_digits_share={int(k): round(float(v), 4) for k, v in vn.value_counts(normalize=True).sort_index().items()},
                         abnormal_digits_share={int(k): round(float(v), 4) for k, v in va.value_counts(normalize=True).sort_index().items()})
    out["format_leak"] = leak
    out["abnormal"]["record_abs_mean_median"] = round(float(abnormal.groupby("rec").AI2_Current.mean().abs().median()), 1)
    (OUT / "facts_extra.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
