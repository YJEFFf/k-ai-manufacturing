# 프레스 v2 후보 고정 비교 (press_advance)

정상 전류 동역학 후보 5개를 같은 분할·전처리·보정으로 비교한 탐색 실험이다. 최종 모델 v2(`early6_ar2`)가 여기서 나왔다. 설계는 [protocol.json](protocol.json)에 있다. 이미 본 이상 21구간을 다시 쓰므로 독립 검증이 아니다. 프로토콜과 결과는 같은 커밋(`bb0bc94`)에 올라가 사전 등록이 아니다. **대회 보고서가 아니다.**

- **후보:** `baseline_w8`(v1과 같은 점수), `early_w6_to_w8`, `ar2_only`, `maxz_ar2`, `early6_ar2`
- **적합·보정:** 정상 학습 구간만으로 적합하고, 정상 보정 구간의 기록구간 최댓값으로 conformal 문턱을 정한다(α 1·3·5%). 분할 A/B와 matched 전처리는 v1과 같다.
- **입력 정밀도 스트레스:** matched로 적합·보정한 상태를 고정하고, 평가 입력만 raw·coarse로 바꿔 다시 잰다.

## 결과 파일

| 파일 | 내용 |
|---|---|
| [metrics.csv](metrics.csv) | 180행 = 분할 2 × 후보 5 × 입력 3(matched·raw·coarse) × 기준 2(conformal·cutoff) × α 3 |
| [primary.csv](primary.csv) | 주 조건 10행(conformal, α=1%, matched) |
| `segment_metrics.csv` | 기록구간 단위 원표 30,780행. Git에서 뺐고 실행하면 생긴다 |
| [manifest.json](manifest.json) | 프로토콜, 적합 계수, 입력 해시, v1 코드 묶음 해시, 스크립트 해시, 결과 해시, 실행 환경 |

주 조건(α=1%, matched)에서 `early6_ar2`는 미탐 행 A 44·B 31, 정상 알림 A 0/120·B 3/180, F1 A 0.961938·B 0.970990이다. 다른 후보는 [primary.csv](primary.csv)에 있다.

**다른 패키지와의 연결.** `press_guard/train.py`는 학습 뒤 `primary.csv`의 `early6_ar2` 행과 TP/FP/FN·F1이 같은지 확인한다. `press_guard/analyze.py`는 `metrics.csv`(통합 비교·입력 정밀도 강건성)와 `manifest.json`(입력 해시, 스크립트 해시)을 읽는다. 스크립트를 고치면 다시 실행해야 `analyze.py`가 통과한다.

## 재현과 검증

`yejun/`에서 실행한다(PowerShell은 첫 줄 대신 `$env:OMP_NUM_THREADS=1; $env:PYTHONDONTWRITEBYTECODE=1`). 시간은 이 기기(Apple M2) 실측이다.

```bash
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python analysis/press_advance/run_experiment.py                          # 약 7초, 결과를 이 폴더에 쓴다
python analysis/package_contract.py --package analysis/press_advance     # 실행 기록 무결성 + 동결 기대값 비교
python -m pytest -q analysis/press_advance/test_contract.py              # 변조·삭제 검출
```

공용 검사기 [package_contract.py](../package_contract.py)가 [contract.json](contract.json)에 따라 다음을 확인한다(평가관 06 R8).
- 실행 기록의 스크립트 해시·v1 코드 묶음 해시·입력 해시·결과 해시가 현재 파일과 같은가
- `metrics.csv`·`primary.csv`가 [expected/](expected)의 동결값과 같은가(수치 허용오차 1e-9, 문자 정확 비교)
- `segment_metrics.csv`는 있으면 실행 기록 해시와 같아야 하고, 동결에는 행 수·열만 남긴다. 없으면(갓 받은 사본) 실패가 아니라 참고로 알린다.

결과를 바꾸거나 지우면, 실행 뒤 코드·입력이 바뀌면, 동결값을 바꾸면 실패한다. 동결(`--freeze`)은 무결성이 통과한 실행만 받는다.
