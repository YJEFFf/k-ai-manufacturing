"""③ 프레스: 수집 형식 지름길(전류 격자·진동 소수 자릿수) 감사와 재양자화 후 성능 재평가.

1) 원본에서 형식만 보는 규칙 2개의 F1을 잰다.
2) 두 날짜에 같은 양자화를 적용한다 (matched / coarse 두 단계).
3) 변환 후 지름길 규칙이 무너지는지 확인한다.
4) 예준 press_policy_audit.py(분할·예산·분모 고정)를 변환본마다 그대로 돌려 비교한다.

실행: python code/press/05_requantize_audit.py [--audit <press_policy_audit.py 경로>]
"""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "3_소성가공_예지보전"
OUT = HERE / "outputs" / "requantize"
# 팀 레포에서는 claude/code/press/ → 레포 루트/codex/... 를 기본으로 쓴다
DEFAULT_AUDIT = HERE.parents[2] / "codex" / "analysis" / "press_welding_review" / "press_policy_audit.py"
VIB = ["AI0_Vibration", "AI1_Vibration"]
CUR = "AI2_Current"
Q_CUR = 1.1920929  # 이상 파일 전류값이 전부 놓인 격자 간격

VARIANTS = {
    "raw": None,
    "matched": dict(vib=1e-4, cur=Q_CUR),       # 두 파일 해상도를 모두 덮는 최소 공통 양자화
    "coarse": dict(vib=1e-3, cur=4 * Q_CUR),    # 더 거칠게: 신호가 해상도에 기대는지 확인
}


def shortcut_rules(df):
    """형식만 보는 규칙. 1이면 '이상 파일 형식'."""
    r = df[CUR] / Q_CUR
    on_grid = (np.abs(r - np.round(r)) < 1e-3).astype(int)
    fine = np.zeros(len(df), dtype=int)
    for c in VIB:  # 소수 6자리보다 더 세밀한 값이 있는가
        x = df[c] * 1e6
        fine |= (np.abs(x - np.round(x)) > 1e-3).astype(int)
    return {"current_on_grid": on_grid, "vib_finer_than_1e-6": fine,
            "either": on_grid | fine}


def quantize(df, spec):
    out = df.copy()
    if spec is None:
        return out
    for c in VIB:
        out[c] = np.round(out[c] / spec["vib"]) * spec["vib"]
    out[CUR] = np.round(out[CUR] / spec["cur"]) * spec["cur"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT,
                    help="예준 codex/analysis/press_welding_review/press_policy_audit.py")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abn = pd.read_csv(DATA / "outlier_data.csv")

    rows = []
    for name, spec in VARIANTS.items():
        n2, a2 = quantize(normal, spec), quantize(abn, spec)
        both = pd.concat([n2, a2], ignore_index=True)
        for rule, pred in shortcut_rules(both).items():
            rows.append(dict(variant=name, rule=rule,
                             f1=f1_score(both["Equipment_state"], pred),
                             flagged_normal=int(pred[: len(n2)].sum()),
                             flagged_abn=int(pred[len(n2):].sum())))
        zpath = OUT / f"press_{name}.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for fname, d in (("press_data_normal.csv", n2), ("outlier_data.csv", a2)):
                z.writestr(f"press/{fname}", d.to_csv(index=False, float_format="%.10g"))
        res = OUT / name
        res.mkdir(exist_ok=True)
        subprocess.run([sys.executable, str(args.audit), "--zip", str(zpath), "--output", str(res)],
                       check=True, stdout=subprocess.DEVNULL)

    sc = pd.DataFrame(rows)
    sc.to_csv(OUT / "shortcut_rules.csv", index=False)
    print(sc.round(4).to_string(index=False))

    frames = []
    for name in VARIANTS:
        m = pd.read_csv(OUT / name / "press_policy_metrics.csv")
        m.insert(0, "variant", name)
        frames.append(m)
    allm = pd.concat(frames, ignore_index=True)
    allm.to_csv(OUT / "policy_metrics_by_variant.csv", index=False)
    print("\ncolumns:", list(allm.columns))


if __name__ == "__main__":
    main()
