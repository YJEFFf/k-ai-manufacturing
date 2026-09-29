"""시각 오류 한 행(튐)의 영향 모의: 대회 이상 파일의 여러 곳에 한 행의 시각을 앞으로 틀리게 넣고 보류·경보 감소·사건 분할을 센다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/tools/spike_scan.py [--split B] [--step 3]

README 「수집 시각 오류」 절의 모의 수치(+5초·+1시간, 표본 대체·끼어듦)를 다시 잰다. 결과는 화면에만 쓴다(동결 대상 아님).
기본은 3행 간격 200곳(macOS 약 40초), --step 1은 모든 위치 598곳(약 2분)이다.
- 표본 대체: 한 행의 시각만 +X초. 끼어듦: 한 행을 복사해 +X초 시각으로 바로 뒤에 넣는다.
- 경보 감소는 튄 행 자체를 뺀 경보 행 수의 감소다. 사건 분할은 튄 행을 뺀 경보 행이 사건 둘 이상에 나뉜 경우다.
- 보류가 생긴 곳은 튄 행을 넣은 원래 행의 자리(기록 첫 행·끝 행·기록 안)로 나눠 센다.
- 대회 이상 파일은 원자료에서 사건 하나라 사건 합침은 여기서 생길 수 없다(합침은 test_time_order.py의 짧은 정상 기록 시험이 본다).
"""
from pathlib import Path
import argparse
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from model import D, ORDER_HELD, TIME_TOL_S, load_bundle  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="B", choices=("A", "B"))
    ap.add_argument("--step", type=int, default=3, help="튐을 넣을 행 간격(기본 3 → 200곳)")
    args = ap.parse_args(argv)
    model = load_bundle(HERE / "artifacts" / f"guard_{args.split}.json")
    _, abnormal, _ = D.load()
    base_frame = D.inputs_only(abnormal).reset_index(drop=True)
    base_pred = model.predict(base_frame)
    base = int(base_pred.alarm.sum())
    times = pd.to_datetime(base_frame[D.TIME])
    fmt = "%Y-%m-%d %H:%M:%S.%f"
    positions = range(1, len(base_frame) - 1, args.step)
    step = times.diff().dt.total_seconds().to_numpy()
    first = np.r_[True, step[1:] > D.DT + TIME_TOL_S]                 # 기록 첫 행(앞 간격이 정상 간격을 벗어남)
    last = np.r_[first[1:], True]                                        # 기록 끝 행
    where = np.where(first, "첫 행", np.where(last, "끝 행", "기록 안"))
    print(f"분할 {args.split}, 원자료 경보 {base}행·사건 {int(base_pred.incident_id.max())}개, 위치 {len(positions)}곳"
          f"(기록 첫 행 {int(first[list(positions)].sum())}·끝 행 {int((last & ~first)[list(positions)].sum())})")
    for seconds in (5, 3600):
        for mode in ("대체", "끼어듦"):
            drops, split, held = [], 0, {"첫 행": 0, "끝 행": 0, "기록 안": 0}
            for i in positions:
                frame = base_frame.copy()
                wrong = (times[i] + pd.Timedelta(seconds=seconds)).strftime(fmt)
                if mode == "대체":
                    frame.loc[i, D.TIME] = wrong
                    spike = i
                else:
                    extra = frame.iloc[[i]].copy()
                    extra[D.TIME] = wrong
                    frame = pd.concat([frame.iloc[:i + 1], extra, frame.iloc[i + 1:]], ignore_index=True)
                    spike = i + 1
                pred = model.predict(frame)
                keep = np.ones(len(pred), bool)
                keep[spike] = False
                drops.append(base - int(pred.alarm.to_numpy()[keep].sum()))
                held[where[i]] += int((pred.time_order_event == ORDER_HELD).any())
                alarms = pred[pred.alarm.eq(1).to_numpy() & keep]
                split += int(alarms.incident_id.nunique() > 1)
            d = np.asarray(drops)
            print(f"+{seconds}초 {mode}: 경보 감소 중앙 {np.median(d):.0f}행·90% {np.quantile(d, .9):.0f}행·최대 {d.max()}행 · "
                  f"보류가 생긴 곳 {sum(held.values())}(" + "·".join(f"{k} {v}" for k, v in held.items()) + f") · 사건 분할 {split}")


if __name__ == "__main__":
    main()
