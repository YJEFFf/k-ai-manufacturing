"""Insert traceable post-hoc results into the separate report copy only."""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from build_hwpx_copy import SRC, verify_protected_sources
from run_experiment import verify_lock, write_json

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
FAMILIES = {
    "current_distortion": "전류 파형 왜곡",
    "vibration_noise": "진동 잡음",
    "vibration_impulse": "진동 감쇠 충격",
    "vibration_amplification": "진동 지속 증폭",
}


def pair(rows, column, format_spec=".3f"):
    return " / ".join(format(float(rows.loc[s, column]), format_spec) for s in ("A", "B"))


def main():
    verify_protected_sources()
    lock = verify_lock(OUT / "selection_lock.json")
    selected = lock["selected"]
    if not selected:
        raise RuntimeError("No selected candidate: write an explicit failed-selection report instead")
    audit = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    assert audit["passed"] and audit["lock_sha256"] == lock["lock_sha256"]
    replay = json.loads((OUT / "replay_verification.json").read_text(encoding="utf-8"))
    assert replay["passed"] and replay["selection_lock_sha256"] == lock["lock_sha256"]
    selection = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    actual = pd.read_csv(OUT / "actual_metrics.csv")
    primary = actual[(actual.alpha == .01) & (actual.abnormal_subset == "all21")]
    back = actual[(actual.alpha == .01) & (actual.abnormal_subset == "back11")]
    injections = pd.concat([pd.read_csv(OUT / f"{s}_injection.csv") for s in ("A", "B")])
    stress = pd.concat([pd.read_csv(OUT / f"{s}_stress.csv") for s in ("A", "B")])
    base = primary[primary.model == "V2"].set_index("split")
    chosen = primary[primary.model == selected].set_index("split")
    bbase = back[back.model == "V2"].set_index("split")
    bchosen = back[back.model == selected].set_index("split")
    family = injections.groupby(["phase", "model", "family"])[["detection_rate", "control_rate", "paired_increase"]].mean()
    by_strength = injections.groupby(["phase", "model", "family", "strength"])[["detection_rate", "control_rate", "paired_increase"]].mean()
    nuisance = stress[(stress.alpha == .01) & (stress.kind != "stuck")].groupby(["phase", "model", "kind"]).normal_record_fpr.max()
    raw_rows = []
    names = ["V2", selected, "VD3", "OR_V2_VD3", "REF_PCA", "REF_VIB", "REF_AND"]
    labels = {"V2": "기존 v2", selected: "선택된 통합 후보", "VD3": "차분 진동 단독(VD3)",
              "OR_V2_VD3": "개별 α 1% 경보 OR", "REF_PCA": "PCA-MSPC 비교기", "REF_VIB": "진동 거리 비교기", "REF_AND": "두 비교기 최소점수 결합"}
    for model in names:
        rows = primary[primary.model == model].set_index("split")
        raw_rows.append(f"| {labels[model]} | {pair(rows, 'row_f1')} | {pair(rows, 'normal_fp_records', '.0f')} | {pair(rows, 'detected_records', '.0f')} | {pair(rows, 'fn', '.0f')} |")
    injection_rows = []
    for fam, label in FAMILIES.items():
        for strength in sorted(injections[injections.family == fam].strength.unique()):
            rates = {}
            for model in ("V2", selected):
                rates[model] = " / ".join(f"{100*by_strength.loc[(s, model, fam, strength), 'detection_rate']:.1f}%" for s in ("A", "B"))
            injection_rows.append(f"| {label} · 강도 {strength:g} | {rates['V2']} | {rates[selected]} |")
    stress_labels = {"offset": "센서별 상수 이동 ±학습 SD", "gain": "센서별 배율 0.8·1.2", "load": "전류 부하 대리변수 0.5·1.5배", "quantization": "양자화 간격 4배", "jitter": "가정한 시각 흔들림 0.1·0.5ms"}
    stress_rows = []
    for kind, label in stress_labels.items():
        rates = {m: " / ".join(f"{100*nuisance.loc[(s,m,kind)]:.1f}%" for s in ("A", "B")) for m in ("V2", selected)}
        stress_rows.append(f"| {label} | {rates['V2']} | {rates[selected]} |")
    dev = selection["selected_metrics"]
    control = {m: [float(family.loc[(s,m)].control_rate.mean()) for s in ("A", "B")] for m in ("V2", selected)}
    macro = {m: [float(family.loc[(s,m)].detection_rate.mean()) for s in ("A", "B")] for m in ("V2", selected)}
    section = f'''## ◦ 2.8 정상 자료로 고정한 진동 보완 실험(사후 †)

- 목적과 구분: 기존 v2의 전류형 탐지를 유지하면서 진동만 변하는 조건의 감시 범위를 넓힐 수 있는지 별도로 시험했다. 이 절은 기존 제출본 c898be2 이후의 추가 연구다. 전체 이상 자료가 이미 팀에 알려진 상태이므로 독립 test나 새 고장 검증으로 부르지 않는다. 기존 잠금 모델·R1·R2·확률 보정은 그대로 보존했다.
- 선택 절차: A·B 공통 정상 학습 범위에서 기록 0~119를 적합, 120~239를 보정, 240~299를 개발 선택에 썼다. 기본·진동 단독 8개와 결합 48개, 독립 구현 참고 비교기 3개로 총 59개를 고정했다. 참고 비교기 3개와 별도 OR 4개는 선택 대상에서 제외했다. 선택 가능 56개 중 정상 개발 오경보 기록률 5% 이하, 각 센서 상수 이동 후 증가 2%p 이하인 {selection['gate_pass_selectable']}개가 관문을 통과했다. 그 안에서 주입 가족별 평균 탐지율의 최솟값, 전체 가족 평균, 낮은 최악 섭동 경보율, 단순성 순서로 골랐다. 실제 이상 파일을 열기 전에 선택·설정·코드 해시를 잠갔다.
- 고정한 모델: {selected}는 기존 v2와 진동 차분 예측 잔차의 최근 3개 점수 평균(VD3)을 결합한다. VD3는 같은 기록의 과거 최대 5행에서 세 센서의 차분을 입력받아 현재 진동 2채널의 차분을 Ridge로 예측하고, 정상 잔차에 Ledoit–Wolf 수축 공분산 추정[29]을 적용한 Mahalanobis 제곱거리로 채점한다. 과거 전류도 입력이므로 전류와 완전히 독립된 경로는 아니다. 기록 경계에서 초기화하며 VD3 첫 점수는 5번째 행부터 가능하다. v2는 그 전에도 사용할 수 있는 성분으로 판단한다.
- 하나의 경보 예산: 두 경로 점수를 각 정상 train의 꼬리 척도 g로 변환한 뒤 S=max(g(v2), g(VD3))로 합쳤다(진동 가중치 1). 정상 calibration 각 기록의 최대값 M을 한 번 보정하여 p=(1+M≥S인 기록 수)/121, p≤0.01일 때 경보한다. 최소 p는 1/121이므로 두 경로를 각각 α 0.5%로 나누면 경보가 불가능하다. 아래의 개별 α 1% OR는 다른 예산의 참고 대조다.
- 정상 개발에서 선택 후보의 무주입 오경보는 0/60기록, 상수 이동 후 최대 증가 {100*dev['offset_max_increase']:.2f}%p였다. 가족별 탐지율 최솟값은 {100*dev['minimum_family_detection']:.2f}%, 네 가족 평균은 {100*dev['macro_family_detection']:.2f}%다. 관문은 제한된 조건이며, 전체 섭동 중 최대 경보율은 {100*dev['maximum_stress_fpr']:.2f}%였다. 이 선택만으로 센서 변화 전반에 강건하다고 할 수 없다.

◦ 실제 파일 재평가: R1 없이 모든 행·기록을 분모에 포함

| 모델 | 행 F1 A / B | 정상 오경보 기록 A / B | 이상 탐지 기록 A / B | 이상 미탐 행 A / B |
|---|---:|---:|---:|---:|
{chr(10).join(raw_rows)}

- 정상 분모는 A 120기록·4,090행, B 180기록·6,097행이다. 이상은 앞 10·뒤 11을 합친 21기록·600행이며, 2.4절의 뒤 11기록 표와 분모가 다르다. 위의 기록 탐지는 한 번이라도 경보한 기록 수이고, 행 F1에는 그 기록의 미탐 행도 그대로 남긴다. 비교기의 첫 9행과 짧은 기록도 분모에서 빼지 않았다. PCA-MSPC[6]와 Ledoit–Wolf 수축 공분산 기반 진동 Mahalanobis 제곱거리[29]를 각각 구현하고 동일한 기록 단위 보정을 적용했다. 최소점수 결합은 두 점수를 정상 train 척도로 나눈 뒤 min을 취해 다시 한 번 보정한 값이며, 두 개별 α 경보의 AND가 아니다.
- 기존 표와 같은 뒤 11기록만 보면 v2 행 F1은 {pair(bbase, 'row_f1')}, 통합 후보는 {pair(bchosen, 'row_f1')}이다. 전체 21기록의 최초 경보 지연 중앙값은 v2와 통합 후보 모두 {pair(chosen, 'hit_only_median_delay_s', '.1f')}초이고, 두 모델 모두 미탐 기록은 없다. 이 지연은 각 기록 첫 관측 이후의 값이며 고장 전 선행 시간이 아니다. A·B는 중복 자료여서 두 번의 독립 성공으로 세지 않는다.

◦ 인과적 합성 주입: 강도별 기록 탐지율

| 주입 가족·강도 | 기존 v2 A / B | 통합 후보 A / B |
|---|---:|---:|
{chr(10).join(injection_rows)}

- 위 값은 상·하부 대상 채널(전류는 전류만), 시작 위치 25%·60%, 평가 seed 811·1217·2027을 같은 비중으로 평균한 것이다. 모든 정상 test 기록이 분모에 남으며 시작 전 표본은 원본과 바이트 단위로 같다. 잡음·충격 강도는 정상 train의 AC 크기, 전류 왜곡은 정상 train의 사인 잔차 크기를 기준으로 한다. 진동 지속 증폭은 정상 train 평균에서의 편차를 강도만큼 추가하는 방식이다. 개발 seed는 101로 분리했고 이전 E1b 생성기와는 조건이 달라 그 탐지율을 그대로 비교하지 않는다.
- 네 가족 평균 탐지율은 v2 {100*macro['V2'][0]:.1f}% / {100*macro['V2'][1]:.1f}%, 통합 후보 {100*macro[selected][0]:.1f}% / {100*macro[selected][1]:.1f}%다. 같은 정상 기록의 무주입 대조 경보율은 각각 v2 {100*control['V2'][0]:.2f}% / {100*control['V2'][1]:.2f}%, 통합 후보 {100*control[selected][0]:.2f}% / {100*control[selected][1]:.2f}%이며, 상세 CSV에 짝지은 증가량·시작 전 경보·미탐·검출한 경우의 지연을 함께 보존했다. 진동 잡음·충격에서 넓어진 감시 범위가 지속적인 진동 증폭 전반의 탐지를 보장하지는 않는다.
- 손실도 있다. B 분할의 전류 파형 왜곡 가족 평균은 {100*family.loc[('B','V2','current_distortion'),'detection_rate']:.2f}%에서 {100*family.loc[('B',selected,'current_distortion'),'detection_rate']:.2f}%로, 지속 진동 증폭은 {100*family.loc[('B','V2','vibration_amplification'),'detection_rate']:.2f}%에서 {100*family.loc[('B',selected,'vibration_amplification'),'detection_rate']:.2f}%로 낮아졌다. 결합 후 한 문턱으로 보정하면 경로별 탐지율이 모두 유지되는 것은 아니다. 주입군별 손실을 포함하여 적용 조건을 판단한다.

◦ 정상 조건 변화: 각 조건군에서 가장 높은 기록 경보율(α 1%)

| 변형 조건군 | 기존 v2 A / B | 통합 후보 A / B |
|---|---:|---:|
{chr(10).join(stress_rows)}

- 부하 변형은 정상 전류만 바꾼 대리 시험으로 실제 설비의 부하–진동 동반 변화를 재현하지 않는다. 시각 흔들림은 전체 정상 기록에 사인을 적합하고 60.6Hz 반송파를 가정해 만든 사후 섭동이다. 실제 표본 시각의 측정이나 인과적 센서 수집 모사는 아니다. 센서값 고정은 별도 CSV에 반응을 보존했으며 센서 고장에 대한 경보까지 정상 오경보 억제의 실패로 해석하지 않는다.

그림 15(5장)에 합성 주입과 정상 조건 변화 결과를 함께 정리했다.

- 채택 범위: 이번 자료에서는 실제 이상 탐지와 정상 오경보를 유지하면서 진동 주입 일부의 탐지가 늘었다. 개선분은 {selected}의 별도 보완 근거로 남긴다. 시각 흔들림·센서 배율 변화의 한계와 단일 사건·사후 설계를 고려하여 기존 공식 모델을 이 후보로 교체했다고 쓰지 않는다. 현장 적용 전에는 새로운 정상 날짜·독립 고장·센서 조건에서 진동 보완 경로의 경보량을 확인해야 한다.
- 비교 범위: 기존 특징 맞춤 5NN·3채널 RidgeForecast 결과는 2.4·2.7·4.3절의 과거 결과다. 이번 고정 격자에는 재실행하지 않았으며 VD3를 기존 Ridge와 같은 모델로 부르지 않는다. 따라서 이번 표는 그 두 모델보다 우수하다는 근거가 아니다.

'''
    text = SRC.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^title:.*$", "title: 결과보고서 북적북적 — 개선본", text, count=1)
    section = section.replace(f"{selected}는", f"{selected} 후보는")
    section = section.replace("- 위 값은 상·하부 대상 채널", "- 주입 탐지와 무주입 대조는 각 기록의 지정한 시작 위치 이후부터 기록 끝까지 경보가 있었는지를 센 값이다. 전체 기록의 정상 오경보율과 집계 범위가 다르다. 위 값은 상·하부 대상 채널")
    heading = "## ◦ 2.8 정상 자료로 고정한 진동 보완 실험(사후 †)"
    chapter = "# □ 제3장."
    if heading in text:
        start, end = text.index(heading), text.index(chapter)
        text = text[:start] + section + text[end:]
    else:
        text = text.replace(chapter, section + chapter, 1)
    summary = f"◦ 사후 보완: 정상 개발 자료로 {selected}를 고정한 뒤 이상 전체 21기록을 재평가함. R1 없는 행 F1 {pair(chosen, 'row_f1')}, 정상 오경보 0/120·3/180이며 진동 주입 일부의 탐지가 늘었음. 센서 조건 변화에 대한 한계는 남아 별도 보완 후보로 제시함(2.8절).\n"
    if "◦ 사후 보완:" not in text:
        text = text.replace("◦ 재현성:", summary + "◦ 재현성:", 1)
    note = "- 추가 정상 전용 선택: 2.8절의 결합 후보는 기존 A·B 공통 정상 학습 범위 안에서만 선택했다. 선택용 정상 기록과 최종 보정·평가 기록을 구분하고, 새 해시 잠금 뒤 기존 이상을 사후 재평가했다. 이 절의 기존 모델 선택 이력과는 별도 절차다.\n\n"
    if note not in text:
        text = text.replace("[그림 6:", note + "[그림 6:", 1)
    addition = "- 별도 보완 실험(2.8절): 전류가 대체로 정상인 진동 잡음·충격에는 정상 전용으로 고정한 차분 진동 잔차 경로가 추가 탐지를 제공했다. 지속 증폭·시각 흔들림까지 해결된 것은 아니며, 결합 모델의 한 문턱 보정과 새 정상 날짜 검증을 거쳐 적용 범위를 정한다.\n\n"
    if addition not in text:
        text = text.replace("# □ 제4장.", addition + "# □ 제4장.", 1)
    operation = "- 신규 통합 후보의 운영 위치(2.8절): 위 Ridge OR는 과거 사후 비교이며, 이번 후보는 두 경로를 합친 점수에 한 번만 경보 예산을 적용한다. 기존 1단계·2단계 결과와 확률 열은 그대로 보존한다. 새 경로를 쓸 때는 전류/진동 중 점수가 높아진 경로, 관측 부족, 수집 조건 점검 여부를 함께 기록하고, 새 보정 없이 기존 v2 확률을 통합 후보의 고장확률로 옮기지 않는다.\n\n"
    if operation not in text:
        text = text.replace("## ◦ 4.4 데이터 수집 개선 권고", operation + "## ◦ 4.4 데이터 수집 개선 권고", 1)
    novelty = "◦ 추가 기여(사후, 2.8절): 기존 전류 모델과 차분 진동 잔차를 합친 뒤 정상 기록 최대값으로 한 경보 예산을 보정하고, 정상 전용 선택·시작 전 불변 주입·참조 재생으로 추가 탐지와 실패 조건을 함께 남겼다. 개선 폭은 같은 자료의 실측 범위로 한정한다.\n\n"
    if "◦ 추가 기여(사후, 2.8절):" in text:
        text = re.sub(r"(?m)^◦ 추가 기여\(사후, 2\.8절\):.*$", novelty.rstrip(), text)
    else:
        text = text.replace("# □ 제6장.", novelty + "# □ 제6장.", 1)
    caption = "[그림 15: 정상 자료에서 고정한 통합 후보의 합성 주입 탐지와 정상 조건 변화 민감도. A·B는 중복 자료이며, 평균 탐지율과 조건군 내 최악 경보율을 구분한다. 모든 경보는 R1 없는 α 1% 기록 보정 결과다.]\n\n"
    if "[그림 15:" not in text:
        text = text.replace("# □ 제6장.", caption + "# □ 제6장.", 1)
    evidence = '''◦ 신규 사후 실험의 별도 재현(2.8절)
  - 저장소의 yejun/analysis/press_frontier_improvement_2026-10-08/에서 requirements-windows-lock.txt로 Windows 실험 환경을 설치한다(Python 3.14.7). 기존 제출 ZIP의 Python 3.13 실행 이력과 구분한다.
  - run_experiment.py --data-dir 원본CSV폴더 --output 새결과폴더 --phase all로 정상 전용 선택부터 잠금·A/B 재평가를 실행한다. 이미 잠긴 폴더는 --phase evaluate로 평가만 재현하며, 새 선택은 별도 출력 폴더에 남긴다. 실제 명령·데이터 위치는 같은 폴더 README.md에 적었다.
  - 선택은 config.json·development_candidates.csv·selection.json·selection_lock.json, 실제 평가는 actual_metrics.csv, 주입/섭동은 A/B_injection.csv·A/B_stress.csv, 행 예측과 짝지은 상세 기록은 outputs/local/에 보존한다. verify_results.py는 저장 예측에서 혼동행렬·기록 탐지·conformal 순위 경보·주입 집계를 다시 계산한다.
  - verify_replay.py는 각 분할의 이상 전체 21기록과 길이·위치로 지정한 정상 대표 기록에서 선택 후보와 v2의 한 행/임의 청크/기록 단위 참조 재생을 비교한다. 실제 시험 범위와 차이는 replay_verification.json에 저장한다. 기록 ID를 입력받아 현재 기록의 prefix를 다시 계산하는 참조 구현으로, 현장 스트림 파서나 PLC 배포 성능을 검증한 것은 아니다.
  - 보고서는 복사 원고만 수정하고 build_hwpx_copy.py로 한컴 양식 HWPX/PDF를 별도 생성했다. audit_hwpx_pdf.py가 원고·표·그림 설명 포함 여부, 페이지 밖 글자, 표지 서명란을 확인한다. 원본 보고서·PDF·HWPX·제출 ZIP의 해시는 source_manifest.json과 대조한다.

'''
    if "◦ 신규 사후 실험의 별도 재현(2.8절)" not in text:
        text = text.replace("◦ 주요 참고문헌(방법·평가 근거)", evidence + "◦ 주요 참고문헌(방법·평가 근거)", 1)
    reference = "    * [29] Ledoit, O., Wolf, M. A well-conditioned estimator for large-dimensional covariance matrices. Journal of Multivariate Analysis 88(2):365–411, 2004. DOI: 10.1016/S0047-259X(03)00096-4.\n\n"
    if "    * [29]" in text:
        text = re.sub(r"(?m)^    \* \[29\].*$", reference.rstrip(), text)
    else:
        text = text.replace("※ 경진대회 만족도", reference + "※ 경진대회 만족도", 1)
    SRC.write_text(text, encoding="utf-8", newline="\n")

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    colors = ["#667b91", "#137e80"]
    for col, split in enumerate(("A", "B")):
        ax = axes[0, col]
        x = np.arange(len(FAMILIES))
        for k, model in enumerate(("V2", selected)):
            values = [100*family.loc[(split, model, f), "detection_rate"] for f in FAMILIES]
            bars = ax.bar(x+(k-.5)*.35, values, .35, label="기존 v2" if k == 0 else "통합 후보", color=colors[k])
            ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=8)
        ax.set_xticks(x, ["전류 왜곡", "진동 잡음", "진동 충격", "진동 증폭"])
        ax.set_ylim(0, 100); ax.set_ylabel("기록 탐지율 (%)")
        ax.set_title(f"분할 {split} · 합성 주입 가족별 평균"); ax.legend(frameon=False)
        ax = axes[1, col]
        kinds = ["offset", "gain", "load", "quantization", "jitter"]
        x = np.arange(len(kinds))
        for k, model in enumerate(("V2", selected)):
            values = [100*nuisance.loc[(split, model, f)] for f in kinds]
            bars = ax.bar(x+(k-.5)*.35, values, .35, color=colors[k])
            ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=8)
        ax.set_xticks(x, ["상수 이동", "센서 배율", "전류 배율", "양자화", "시각 흔들림"], rotation=15)
        ax.set_ylim(0, 110); ax.set_ylabel("정상 기록 경보율 (%)")
        ax.set_title(f"분할 {split} · 조건군 내 최악값")
    fig.suptitle("진동 주입 감시 범위는 확대됐지만, 수집 조건 민감도는 남는다", fontsize=14)
    figure = SRC.parent / "figures/fig15_frontier_evaluation.png"
    fig.savefig(figure, dpi=180, facecolor="white")
    plt.close(fig)
    write_json(HERE / "figure_map.json", {"15": figure.name})
    write_json(OUT / "report_facts.json", dict(selected=selected, lock_sha256=lock["lock_sha256"],
        actual_primary=primary[primary.model.isin(names)].to_dict(orient="records"),
        injection_family=family.reset_index().query("model in @names").to_dict(orient="records"),
        source_tables=["actual_metrics.csv", "A_injection.csv", "B_injection.csv", "A_stress.csv", "B_stress.csv", "selection.json"],
        figure=figure.name, report_source=str(SRC), protected_sources_unchanged=True))
    verify_protected_sources()
    print(f"Updated {SRC}; figure {figure}; evidence {OUT / 'report_facts.json'}")


if __name__ == "__main__":
    main()
