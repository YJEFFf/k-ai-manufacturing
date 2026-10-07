"""4단계(사후, test 채점 뒤): 선택된 LSTM과 기준 모델의 오류 조건을 같은 정의로 비교한다(PROTOCOL.md 6절).

① 운전 상태별 오경보: 정상 valid+test 기록 중 실시간 경보가 1행이라도 난 기록 수(α 1·3·5%).
   보고서 3.2절 표와 같은 정의다. 상태는 준용 domain/outputs/06_operating_regime_records.csv를 그대로 쓴다.
   valid 행은 LOO p, test 행은 전체 보정 p이고 R1은 흐름 안에서만 이어진다(evalcore.predict_rows).
② 미탐 위치: 이상 행 중 놓친 행의 기록 안 위치(0, 1, 2~7, 8~19, 20 이상), valid·test, α 1%.
③ 첫 경보 지연: 이상 기록마다 첫 경보까지의 행 수(0.1초 단위), 규칙 없는 모델과 R1 모델.
출력: outputs/04_states.csv, 04_miss_position.csv, 04_first_alarm.csv, 04_conditions.json
실행: PYTHONDONTWRITEBYTECODE=1 python 04_conditions.py
"""
from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402
import lx_scoring as X  # noqa: E402

TRAIN_VALID_END = {"A": (360, 480), "B": (300, 420)}   # tvt/lib.SPLITS와 같은 정상 기록 번호 경계
STATES = ["quiet", "busy_low", "busy_mid", "busy_high", "busy_short"]
POS_BINS = [(0, 0, "0"), (1, 1, "1"), (2, 7, "2~7"), (8, 19, "8~19"), (20, 10 ** 6, "20+")]


START = ("W20-none-64x32-e300p30", "raw-last")


def models_to_run(sel: dict) -> list[tuple[str, str, bool, bool]]:
    """(표시 이름, 점수 열, R1, R2). LSTM은 새 시드 앙상블(e345, 주 결과)과 선택 시드 앙상블(e012)."""
    s = sel["track_L"]
    out = []
    for ens in ("e345", "e012"):
        n = X.vname(s["cfg"], s["scoring"], ens)
        out += [(f"L:{ens}", n, False, False), (f"L+R1:{ens}", n, True, False)]
    out.append(("start:e012", X.vname(START[0], START[1], "e012"), False, False))
    out += [("v2", "v2", False, False), ("v2+R1", "v2", True, False), ("v2+R1+R2", "v2", True, True),
            ("mlp_ae5", "mlp_ae5", False, False), ("lstm20(행 표)", "lstm20", False, False)]
    return out


def main():
    sel = json.loads((H.OUT / "02_selection.json").read_text(encoding="utf-8"))
    _, ev, _ = H.tvt()
    states = pd.read_csv(H.DOMAIN_OUT / "06_operating_regime_records.csv", encoding="utf-8-sig").set_index("rec")["state"]
    cfgs = {sel["track_L"]["cfg"], START[0]}
    st_rows, miss_rows, first_rows = [], [], []
    for sid in H.SPLITS:
        t, meta, _ = X.build_variant_table(sid, cfgs=cfgs, singles=False, ens_sets=("e012", "e345"))
        r2 = meta["r2_ref"]
        tr_end, va_end = TRAIN_VALID_END[sid]
        for label, col, h1, h2 in models_to_run(sel):
            c = (label, col, h1, h2, False, 1)
            for a in H.ALPHAS:
                preds = []
                for regime in ("valid", "test"):
                    p = ev.predict_rows(t, c, a, regime, r2).assign(part=regime)
                    preds.append(p)
                p = pd.concat(preds, ignore_index=True)
                p["alarm"] = p.alarm_realtime.astype(bool)
                # ① 정상 기록 → 원 기록 번호 → 운전 상태
                nm = p[p.subset == "normal"].copy()
                k = nm.rec.str.split(":").str[2].astype(int)
                nm["orig"] = np.where(nm.part == "valid", k + tr_end, k + va_end)
                per = nm.groupby(["part", "orig"]).alarm.max().reset_index()
                per["state"] = per.orig.map(states)
                for part in ("valid", "test", "valid+test"):
                    q = per if part == "valid+test" else per[per.part == part]
                    for s in STATES + ["all"]:
                        qq = q if s == "all" else q[q.state == s]
                        st_rows.append(dict(split=sid, model=label, alpha=a, part=part, state=s,
                                            records=int(len(qq)), fa_records=int(qq.alarm.sum())))
                if a != H.PRIMARY_ALPHA:
                    continue
                # ② 미탐 위치
                ab = p[p.subset == "abnormal"]
                for part in ("valid", "test"):
                    q = ab[ab.part == part]
                    for lo, hi, name in POS_BINS:
                        m = (q.pos >= lo) & (q.pos <= hi)
                        miss_rows.append(dict(split=sid, model=label, part=part, pos_bin=name, rows=int(m.sum()),
                                              missed=int((m & ~q.alarm).sum())))
                # ③ 첫 경보 지연(행 수)
                for (part, rec), g in ab.groupby(["part", "rec"], sort=False):
                    hit = np.flatnonzero(g.alarm.to_numpy())
                    first_rows.append(dict(split=sid, model=label, part=part, rec=rec, n=int(len(g)),
                                           first_alarm_row=int(g.pos.to_numpy()[hit[0]]) if len(hit) else None))
        print(sid, "완료", flush=True)
    st, miss, first = pd.DataFrame(st_rows), pd.DataFrame(miss_rows), pd.DataFrame(first_rows)
    st.to_csv(H.OUT / "04_states.csv", index=False)
    miss.to_csv(H.OUT / "04_miss_position.csv", index=False)
    first.to_csv(H.OUT / "04_first_alarm.csv", index=False)

    # 보고서 3.2절 표 모양: 분할 B, valid+test, α 5%(차이가 보이게) — 시드 모델은 시드 평균
    def table(alpha, split="B"):
        q = st[(st.split == split) & (st.alpha == alpha) & (st.part == "valid+test")].copy()
        q["group"] = q.model.str.replace(r":s\d$", ":seed-mean", regex=True)
        g = q.groupby(["group", "state"]).agg(records=("records", "first"), fa_records=("fa_records", "mean")).reset_index()
        return g.pivot(index="state", columns="group", values="fa_records").reindex(STATES + ["all"]).round(2)

    out = {f"states_B_alpha{int(a * 100)}": table(a).reset_index().to_dict("records") for a in H.ALPHAS}
    out["state_records_B"] = st[(st.split == "B") & (st.alpha == 0.05) & (st.part == "valid+test") & (st.model == "v2")] \
        .set_index("state").records.to_dict()
    mt = miss[miss.part == "test"].groupby(["model", "pos_bin"]).agg(rows=("rows", "sum"), missed=("missed", "sum")).reset_index()
    out["test_miss_by_position_AplusB"] = mt.to_dict("records")
    fa = first[first.part == "test"].groupby(["split", "model"]).first_alarm_row.agg(
        detected="count", median="median", max="max").reset_index()
    out["test_first_alarm"] = fa.to_dict("records")
    H.dump(out, H.OUT / "04_conditions.json")
    pd.set_option("display.width", 250)
    for a in H.ALPHAS:
        print(f"\n== 분할 B valid+test 정상 기록 중 경보 기록 수, α {a}")
        print(table(a).to_string())
    print(mt.pivot(index="model", columns="pos_bin", values="missed").to_string())


if __name__ == "__main__":
    main()
