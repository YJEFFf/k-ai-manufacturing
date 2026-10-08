# 북적북적 통합 코드 제출본

결과보고서의 공식 모델(기반 모델 v2 + 규칙 R1·R2, 두 단계 경보)과 2.8절 사후 보완 실험, 같은 조건 비교·정상 조건 민감도 등 추가 감사를 이 폴더 하나에서 다시 만듭니다. 원본 CSV 2개와 필요한 팀 모듈이 들어 있어 저장소나 보고서 편집 프로그램이 필요하지 않습니다.

## 0. 설치 없이 확인(수 초)

```console
python check_bundled.py
```

파이썬 표준 라이브러리만 씁니다. 세 가지를 확인합니다.

- `package_manifest.json`의 해시로 배포 파일이 바뀌지 않았는지 봅니다.
- 동봉한 공식 test 예측 파일의 해시를 `expected_results.json`과 대조합니다.
- 같은 파일의 `label`과 경보 열로 행 F1을 다시 계산합니다. 공식 성능 1단계 v2+R1은 1.000·0.995, 2단계 v2+R1+R2는 1.000·1.000, 기반 모델 v2는 0.965·0.970입니다.

공식 test 예측 파일은 `reference_results/official_predictions/test_predictions_A.csv`, `test_predictions_B.csv`입니다. 전체를 실행하면 같은 파일을 `predictions/`에 다시 만들고 해시를 대조합니다.

## 1. 설치

Python 3.14에서 압축을 풀고 가상환경에 설치합니다. 패키지 설치에만 인터넷이 필요합니다.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

macOS/Linux에서는 `.venv/bin/python`을 씁니다. 아래 명령의 `python`은 이 가상환경의 파이썬입니다. 가상환경을 켜지 않았다면 `.venv\Scripts\python run_all.py`처럼 경로를 붙입니다. `run_all.py`는 자신을 실행한 파이썬으로 하위 단계를 돌립니다. 압축 해제 경로에 공백이나 한글이 있어도 됩니다.

## 2. 실행

```console
python run_all.py
```

한 명령으로 다음을 차례로 실행합니다.

- 기존 26단계: 전처리 → 학습 → 추론 → test 예측 파일 → 보고서 수치 대조 43항목
- 2.8절 사후 보완 실험: 정상 전용 선택 → 잠금 → 평가 → 재계산·재생·독립 수식 감사 → 모델 동결
- 추가 감사: 같은 조건 비교, 정상 조건 민감도, 공식 규칙 상수 민감도, 두 단계 경보 재생·경보량
- 계약 검사(pytest)

추가 감사 결과는 `reference_results/extra_audits/`의 기준표와 자동으로 대조합니다. 단계 로그는 `logs/`, 전체 결과는 `logs/integrated_run_summary.json`에 남습니다. 하나라도 실패하면 종료 코드가 0이 아닙니다.

| 명령 | 내용 |
|---|---|
| `python run_all.py` | 전체(위 목록) |
| `python run_all.py --skip-extra-audits` | 추가 감사 제외 |
| `python run_all.py --section official` | 기존 26단계만(대조 43항목) |
| `python run_all.py --section official --quick` | 기존 빠른 부분(대조 28항목) |
| `python run_all.py --section improvement` | 2.8절 실험과 그 추가 감사 |
| `python run_all.py --verify-only` | 이 폴더에서 이미 실행한 결과를 다시 검사(새로 푼 폴더에서는 안내 후 종료) |

기존 단계(`run_official.py`)는 시작할 때 "결과는 파이썬 3.13에서 만들었다"는 안내를 출력합니다. 기존 결과를 처음 만든 환경을 알리는 문장입니다. 이 배포본의 3.14 판에서도 대조 43항목이 모두 일치했습니다(`verification/`). 처음 쓰던 3.13 실행 설명은 `README_original.md`에 보존했습니다. `environment_original.yml`은 예전 conda 설정이며, 현재 `requirements.txt`를 설치합니다.

## 3. 결과 위치

| 위치 | 내용 |
|---|---|
| `predictions/` | 실행 뒤 다시 만든 공식 test 예측 파일(동봉본은 `reference_results/official_predictions/`) |
| `code/press/*/outputs/` | 기존 파이프라인 산출물(보고서 1~4장 표·그림의 원자료) |
| `yejun/analysis/press_improvement/outputs/` | 2.8절 실험의 선택 기록·잠금·평가표, 같은 조건 비교(`strong_baselines/`)·정상 조건 민감도(`normal_sensitivity/`) |
| `yejun/analysis/press_official_sensitivity/outputs/` | 공식 규칙 상수 민감도와 이상 기록 앞뒤 교차 평가 |
| `yejun/analysis/press_stage_replay/outputs/` | 두 단계 경보의 한 행 재생 일치, 정상 자료 경보량 |
| `logs/` | 단계별 로그와 실행 요약 |

## 4. 검증 기록

`verification/`에는 이 배포본과 계산 파일이 같은 빌드를 새 가상환경·새 압축 해제 폴더에서 `python run_all.py`로 끝까지 실행한 기록(단계별 시간, 결과)이 있습니다. 그 빌드의 SHA-256과 이 배포본이 그 기록 파일만 더했다는 사실은 `package_manifest.json`의 `verification_basis`에 있습니다.

## 5. 새 수집 자료 평가

전체 또는 개선 실행 후 `yejun/analysis/press_improvement/outputs/frozen_holdout/provenance.example.json`을 복사해 실제 수집 출처·설비·사건 정보를 작성합니다. 새 자료는 같은 공정, 센서·단위, 10 Hz 표본 간격이어야 합니다. 아래 명령은 지정한 A 상태를 사용하며 새 자료로 재학습·재보정·후보 선택을 하지 않습니다.

```console
python yejun/analysis/press_improvement/validate_holdout.py evaluate --artifact yejun/analysis/press_improvement/outputs/frozen_holdout --split A --csv new_session.csv --provenance provenance.json --output new_validation
```

정답 0/1 열이 있으면 `--label-column 정답열이름`, 기록 경계 열이 있으면 `--record-column 기록열이름`을 추가합니다. 정답이 없으면 경보 건수만 출력하며 탐지율·오경보율이라고 부르지 않습니다. 기존 파일 전체·부분·재명명·시간 이동 사본은 중복 검사로 거부합니다. 출처 선언과 중복 통과만으로 별개 고장 사건임이 입증되지는 않습니다.

## 6. 범위

- 공식 제출 모델과 추가 실험 모델의 결과를 따로 출력합니다. 추가 감사는 공식 모델·문턱·규칙을 바꾸지 않습니다.
- 이미 관찰한 같은 고장 자료를 재생·재계산하는 검증은 새 설비·새 고장 사건의 일반화 검증과 다릅니다. 이상 21기록은 21개의 독립 고장 사건이 아닙니다.
- 2.8절 실험의 분할·주입·선택 기준은 `yejun/analysis/press_improvement/PROTOCOL.md`에 있습니다. 이 배포본은 선택 대상이 아니었던 참고 계산 3개를 빼고, 남은 56개 후보와 OR 4개의 계산은 원래 코드와 구문(AST) 단위로 같습니다. 원래 선택 잠금의 해시는 `package_manifest.json`에 있으며, 실제 실행은 정상 전용 선택부터 새로 하여 `outputs/selection_lock.json`을 만듭니다.
