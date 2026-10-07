# 북적북적 통합 코드 제출본

기존 보고서의 공식 모델·예측 파일·대조 실험과 개선본의 정상 전용 후보 선택, 진동 잔차 결합, 인공 주입, 계측 섭동 및 재생 검증을 함께 실행합니다. 원본 CSV 2개와 필요한 팀 모듈을 포함하므로 Git 저장소 경로나 별도의 보고서 편집 프로그램이 필요하지 않습니다.

## 실행

Python 3.14 환경에서 압축을 풀고 다음 명령을 실행합니다. 패키지 설치에만 인터넷 연결이 필요합니다.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run_all.py
```

macOS/Linux에서는 `.venv/bin/python`을 사용합니다. 설치 이후의 실험은 인터넷 없이 실행할 수 있습니다. 압축 해제 경로에 공백이나 한글이 있어도 됩니다. 전체 실행은 CPU 성능에 따라 수십 분 이상 걸릴 수 있습니다. 각 단계 로그는 `logs/`, 전체 실행 결과는 `logs/integrated_run_summary.json`에 남습니다. 하나라도 실패하면 종료 코드가 0이 아닙니다.

```console
python run_all.py --section official
python run_all.py --section improvement
python run_all.py --verify-only
python run_all.py --extra-audits
```

`--section official`은 기존 전체 26단계를 실행합니다. `--section improvement`는 개선 실험 전체를 실행합니다. `--quick`은 기존 파이프라인 일부만 실행하므로 전체 보고서 검증용으로 쓰지 않습니다. `--verify-only`는 이미 생성된 결과의 수치·소스·재생 일치를 다시 검사합니다.

추가 감사가 포함된 배포본에서 `--extra-audits`를 주면 같은 조건의 특징 맞춤 5NN·3채널 Ridge 대조와 정상 조건 민감도 시험도 실행합니다. 추가 감사는 기존 선택 모델·문턱을 바꾸지 않습니다. 처음 실행할 때 지정하며 이미 결과가 있는 폴더에서는 새로 압축을 풀어 실행합니다. 포함 여부는 `package_manifest.json`의 `optional_audits_included`로 확인할 수 있습니다.

정상 조건 민감도 시험 후에는 상세 행 기록에서 집계를 별도로 계산하고, 주입 전 불변성·사전 잠금·집계 CSV와의 일치를 다시 확인합니다. 결과는 `outputs/normal_sensitivity/aggregation_verification.json`에 남습니다.

같은 소스·자료로 기본 개선 실험을 이미 마쳤다면 `python run_all.py --section improvement --extra-audits-only`로 기준표 대조와 추가 감사만 실행할 수 있습니다. 이 실행은 기본 모델 선택·평가를 다시 수행했다고 표시하지 않습니다. 추가 감사 결과 폴더도 새로 생성해야 하므로 같은 후속 검사를 중복 실행하려면 기존 산출물을 별도로 보관한 새 압축 해제 폴더를 사용합니다.

## 결과와 검증 범위

- 기존 제출 모델 예측: `predictions/test_predictions_A.csv`, `predictions/test_predictions_B.csv`.
- 개선 실험: `yejun/analysis/press_improvement/outputs/`. 정상 개발 자료로 단독 8개와 결합 48개, 모두 56개 후보 중 하나를 고른 후 실제 이상 데이터를 읽습니다. 후보 격자, 선택, 소스 해시를 먼저 잠급니다. 별도 보정 OR 4개는 선택 대상이 아닙니다.
- 개선 결과 재현 대조: `reference_results/improvement/`의 고정 표와 새로 계산한 표를 비교합니다. 이 폴더는 계산 결과를 대신하지 않습니다.
- 독립 수치 재계산: 저장한 행별 점수로 보정 순위·행 F1·기록 오경보와 주입 대조를 별도 계산합니다. 표본·청크·기록 재생에서 경보 일치도 검사합니다.
- 독립 구현 감사: Ridge 정규방정식과 Ledoit–Wolf 공분산을 별도 수식으로 계산해 진동 차분 점수 및 세 α의 경보를 대조합니다. 결과는 `outputs/independent_implementation_verification.json`입니다.
- 고정 모델 생성: 이번 실행에서 학습한 A/B 상태를 `outputs/frozen_holdout/`의 JSON으로 저장하고 기존 평가 전체 행에서 원래 모델과 점수·경보를 대조합니다. ZIP에는 학습 캐시를 넣지 않았으며 이 상태도 처음부터 생성합니다.
- `package_manifest.json`은 배포 입력의 무결성과 원래 선택 잠금 SHA-256을 기록합니다. 선택 대상이 아니던 비교기 3개를 제외했고, 남은 후보의 계산 구문은 AST로 대조했습니다. 기준표는 과거 결과에서 제외한 비교기 행만 뺀 값입니다. 배포 생성 시각과 역사적 선택 시각을 구분하며, `reference_results`의 잠금은 새 실험 실행을 의미하지 않습니다. 실제 실행에서는 정상 전용 선택부터 새로 수행해 `outputs/selection_lock.json`을 생성합니다.

공식 제출 모델과 추가 실험 모델의 결과를 각각 출력합니다. 이미 관찰한 동일 고장 자료를 재생·재계산하는 검증과 새 설비·새 고장 사건에서의 일반화 검증은 다릅니다. 21개 이상 기록은 21개의 독립 고장 사건이 아닙니다. 세부 분할·주입·선택 기준은 `yejun/analysis/press_improvement/PROTOCOL.md`에 있습니다.

기존 실행 설명은 `README_original.md`에 보존했습니다. 공통 설치 환경은 최상위 `requirements.txt`를 따릅니다.

## 새 수집 자료 평가

전체 또는 개선 실행 후 `yejun/analysis/press_improvement/outputs/frozen_holdout/provenance.example.json`을 복사해 실제 수집 출처·설비·사건 정보를 작성합니다. 새 자료는 같은 공정, 센서·단위, 10 Hz 표본 간격이어야 합니다. 아래 명령은 지정한 A 상태를 사용하며 새 자료로 재학습·재보정·후보 선택을 하지 않습니다.

```console
python yejun/analysis/press_improvement/validate_holdout.py evaluate --artifact yejun/analysis/press_improvement/outputs/frozen_holdout --split A --csv new_session.csv --provenance provenance.json --output new_validation
```

정답 0/1 열이 있으면 `--label-column 정답열이름`, 기록 경계 열이 있으면 `--record-column 기록열이름`을 추가합니다. 정답이 없으면 경보 건수만 출력하며 탐지율·오경보율이라고 부르지 않습니다. 기존 파일 전체·부분·재명명·시간 이동 사본은 중복 검사로 거부합니다. 출처 선언과 중복 통과만으로 별개 고장 사건임이 입증되지는 않으므로 실제 수집·정비 기록과 함께 판단해야 합니다.
