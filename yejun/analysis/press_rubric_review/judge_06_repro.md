# 평가관 6 — 코드 및 재현성(10점)

검수 기준 커밋: `7ff1e1e`. 보완 실험 사전 프로토콜 `a102ecf`, 결과 `875f269`. 평가일: 2026-09-26. 구현 검수 기록이며 대회 보고서가 아니다.

**주관적 근거 충족도: 8.5/10, 합리적 범위 8~9점.** 공식 기준의 “동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행”은 주 모델 v1/v2에서 강한 실행 증거가 있다. 새 클론 재현뿐 아니라 빈 가상환경에 명시한 의존성을 설치해 v2 재학습·저장·CLI 추론 결과까지 다시 확인했다. 새 보완 실험은 실행 코드와 사전 프로토콜은 보존했으나, 기존 패키지 수준의 결과 무결성·의존성 추적 계약은 이어받지 않았다. 실제 심사점수·수상확률의 예측은 아니다.

## 충족한 증거와 직접 수행 결과

기준은 [공식 원문](official_task_extract.txt)의 88~89행과 `press_submission/PLAN.md:178`~187이다. v1의 구현 계획·현재 README·검증기, v2의 학습/저장/순차 추론·계약·검증기, E1/E2/E3의 실행과 manifest 생성 경로를 읽었다. 모든 실행은 기존 산출물을 덮어쓰지 않도록 pytest 임시 폴더·새 클론·시스템 임시 출력 경로를 사용했다.

| 검증 | 직접 확인한 결과 | 근거 파일 |
|---|---|---|
| 현재 환경 v1 pytest | 49/49, 8.77초 | `judge06_pytest_v1.txt` |
| 현재 환경 v2 pytest | 46/46, 14.06초 | `judge06_pytest_v2.txt` |
| 현재 환경 JS 회귀 | 4개 묶음 통과 | `judge06_web_tests.txt` |
| 현재 v1/v2 verify | 각각 39/39, 19/19 | `judge06_verify_v1.txt`, `judge06_verify_v2.txt` |
| v1 새 클론 | 1~5단계 실행→verify 39/39, 필수 집계 32개 수치 차이 0. **LSTM 캐시 사용** | `judge06_clean_repro_v1.txt` |
| v2 새 클론 | 원본 복사→v1 주 예측 재생성→v2 학습/롤링→분석→audit→verify 19/19, 집계 차이 0 | `judge06_clean_repro_v2.txt` |
| 새 가상환경 설치 | Python 3.12.2로 빈 venv 생성, 기존 `requirements.txt`만으로 설치 성공 | `judge06_venv_install.txt` |
| 새 가상환경 pytest | v1 49/49, v2 46/46. v1에는 matplotlib/pyparsing 사용 중단 예고 14건이 있었지만 실패 없음 | `judge06_venv_pytest_v1.txt`, `judge06_venv_pytest_v2.txt` |
| 새 가상환경 v2 A/B 재학습 | 기존 모델·캐시를 쓰지 않고 학습→보정→새 artifact 저장→복원→평가. 12개 운영점/모델 행의 지표 차이 0 | `judge06_venv_train.txt`, `judge06_venv_comparison.json` |
| 새 가상환경 v2 행별 예측 | 정상 A 4,090행/B 6,097행, 이상 각 600행의 수치 차이 0·경보 차이 0 | `judge06_venv_comparison.json` |
| 새 artifact로 CLI 추론 | A 이상 CSV, chunk=128, 600행 처리. 학습 실행 예측과 모든 열 동일 | `judge06_venv_predict.txt`, `judge06_venv_comparison.json` |
| 보완 실험 해시 감사 | E1~E3에 기록된 모든 자체 코드/프로토콜 해시 일치. E1의 A/B artifact 해시·대회 원본 해시·E2 UCI ZIP 해시 일치 | `judge06_hash_audit.py`, `judge06_hash_audit.json` |
| 사전 고정 이력 | 현재 `protocol.json`이 결과 전 커밋 `a102ecf`의 내용과 SHA-256 동일 | `judge06_hash_audit.json` |

새 환경에서도 주 운영점 TP/FP/FN은 A `556/0/44`, B `569/3/31`이었다. 새 환경은 **같은 macOS arm64·같은 Python 3.12.2**다. 다른 OS 검증은 아니다. BLAS 실제 구성도 기존·새 환경이 같았다(NumPy OpenBLAS 0.3.23.dev, SciPy OpenBLAS 0.3.27, 모두 1스레드).

기존 F1~F5를 그대로 미해결 목록에 옮기지 않았다. 현재 v2에는 재적합 민감도·성분 절제·구간 오류 조건·2×2 표, 예측 식별 열, 정확성/성능 회귀 검사의 구분이 있다. 이 산출물 계약을 포함한 현재 테스트·새 클론 verify가 통과했다. v2 최대 메모리도 `train.py`의 `resources.peak_rss_mb`에 기록하므로 과거의 포괄적인 “메모리 미측정” 지적을 반복하지 않는다.

## 수정·보완 목록

### R6-1 — P1: 보완 실험의 결과·의존 코드·기준 모델을 하나의 실행으로 묶는 계약 보완

- **종류:** 구현/추적 계약 공백. 현재 저장 결과의 수치 오류를 발견했다는 뜻은 아니다.
- **위치:** `analysis/press_supplement/fault_injection.py:126`, `uci_v2.py:219`, `recalibration.py:141`. 실제 공유 의존성은 `common.py:14`~16, 기준 모델 읽기는 `common.py:37`~38 및 `recalibration.py:18`이다.
- **확인:** 세 manifest는 `common.py`, 각 실험 스크립트, `protocol.json`만 코드 해시에 포함한다. 결과 CSV/그림/원표 해시나 필수 산출물 검사 계약이 없다. E2는 결합한 `press_external/metrics.csv`와 분할표의 출처 해시를 기록하지 않는다. E3는 주입 크기와 frozen 기준 결과에 쓰는 `guard_A.json` 해시도 기록하지 않는다. E1만 A/B artifact 해시가 있다. `GuardModel.load`가 모델 내부 해시·v1 의존 코드 해시를 검사한다는 보호는 존재하지만, supplement의 결과를 해당 실행의 v2 코드·최종 산출물과 묶는 검증을 대체하지 못한다.
- **재현/근거:** `python analysis/press_rubric_review/judge06_hash_audit.py`에서 자체 코드 해시는 모두 일치하지만 세 실험 모두 `output_hash_contract_present=false`, `shared_dependency_hash_contract_present=false`다. `judge06_hash_audit.json`에는 현재 결과 해시를 검수용으로 별도 계산해 두었다. 이것을 실험 당시 생성된 manifest로 취급하지 않는다.
- **수정 제안:** supplement의 공통 실행 계약에 실제 의존 코드/프로토콜, 원본과 외부 비교표, 사용한 모델, 필수 출력 목록·해시·실행 ID를 기록하고 검증기를 둔다. 실험별 설정·난수 시드와 정확성 검사를 남기고 E1/E2/E3 중 일부만 실행한 상태도 구별한다. 검증용 새 결과는 별도 출력 위치로 생성할 수 있게 한다.
- **완료 기준:** 원본+커밋된 코드에서 재생성한 결과가 기대 집계와 정해진 허용오차로 일치한다. 출력 누락/변경, 공유 모델 코드 변경, 기준 artifact 변경, 외부 비교표 변경을 각각 검사에서 실패 처리한다. 현재 결과의 무결성을 확인한 뒤에만 기대값 갱신을 검토하며, 이번 검수에서는 동결하지 않았다.

### R6-2 — P2: E2 전처리 캐시 키에 코드·변환 설정을 포함

- **종류:** 캐시 무효화 공백. 현재 UCI 수치가 오래된 캐시로 잘못 계산됐다고 판정한 것은 아니다.
- **위치:** `analysis/press_supplement/uci_v2.py:17`, `:98`~115.
- **확인:** 전역 시스템 임시 파일 `press_supplement_uci10hz.npz`를 모든 체크아웃이 공유하며, 캐시 재사용 조건은 ZIP SHA 하나다. 10 Hz 변환 코드·센서별 평균/반복 방식·protocol 버전을 바꿔도 ZIP이 같으면 기존 배열을 사용한다. 원안 `PLAN.md:184`의 코드/전처리까지 포함한 캐시 원칙보다 약하다.
- **수정 제안:** `archive_sha + preprocessing_version/code_sha + channel/resampling_spec`로 캐시 키를 만들고, 읽을 때 배열 shape·유한값·메타데이터를 검사한다. `--no-cache` 또는 작업별 cache 디렉터리도 제공한다. 무관한 전체 모델 학습 설정까지 이 전처리 캐시에 넣을 필요는 없다.
- **완료 기준:** 같은 입력·변환에서는 cache on/off 결과가 같고, 변환 버전/설정을 바꾸면 기존 캐시를 재사용하지 않는다. 손상된 캐시는 명확한 오류 또는 재생성으로 처리한다.

### R6-3 — P2: 실행 환경 manifest의 BLAS 빈 값 보완

- **종류:** 환경 기록 공백. 현재 재현 실패는 아니다.
- **위치:** `press_submission/press/data.py:155`~164, 특히 `:163`; `press_submission/PLAN.md:178`.
- **확인:** 환경 수집이 `np.__config__.get_info`에 의존해 현재 NumPy에서는 `blas: null`을 남긴다. 실제 BLAS 라이브러리·버전·스레드 수는 이번 `threadpoolctl.threadpool_info()` 호출로 확인 가능했다. E1/E2/E3 environment의 `protocol_version`도 공용 v1 값이므로 실험 고유 프로토콜 식별자는 별도 명시하는 편이 정확하다.
- **수정 제안:** 이미 scikit-learn의 의존성인 threadpoolctl 등으로 실제 BLAS/OpenMP 구성과 스레드 수를 기록하고, 실행한 실험 프로토콜·시드는 별도 필드로 남긴다. 사용하지 않은 torch를 모든 실험에 억지로 요구할 필요는 없다.
- **완료 기준:** 동일 환경 재실행 manifest에 현재 backend/version/threads가 빈 값 없이 남고, 보완 실험의 protocol 식별자가 v1 공용 자료 처리 버전과 구별된다. 경로나 실행 시각처럼 달라지는 값과 수치 비교에 필요한 환경 차이를 구분한다.

현재 실행을 막는 P0는 발견하지 못했다. R6-1은 보완 실험 전체를 “추적·검증 가능한 자동 실행”으로 완료 처리하기 전 필요한 조치이고, R6-2/3은 후속 코드 변경과 다른 실행 환경에서의 문제 진단을 위한 보완이다.

## 실행 명령과 확인 범위

기준 작업 디렉터리는 `yejun/`이다. 현재 환경에서는 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`과 `/opt/anaconda3/bin/python`을 사용했다.

```bash
python -m pytest -q -p no:cacheprovider press_submission/tests --basetemp /tmp/press_judge06_v1_tests
python -m pytest -q -p no:cacheprovider press_guard/test_guard.py press_guard/test_serve.py press_guard/test_analyze.py press_guard/test_review_regressions.py --basetemp /tmp/press_judge06_v2_tests
python press_submission/verify.py --out press_submission/outputs
python press_guard/verify.py
node press_guard/test_web.cjs
PATH=/opt/anaconda3/bin:$PATH bash press_submission/tools/clean_repro.sh --with-lstm
PYTHON=/opt/anaconda3/bin/python bash press_guard/tools/clean_repro.sh
python analysis/press_rubric_review/judge06_hash_audit.py
```

빈 환경은 시스템 임시 폴더에 `python -m venv`로 생성한 뒤 `venv/bin/python -m pip install -r press_submission/requirements.txt`를 실행했다. 같은 pytest 명령을 새 Python으로 실행했고, `press_guard/train.py --root press_submission --out <임시>/train_outputs --artifacts <임시>/artifacts`로 새로 적합했다. 새 `guard_A.json`으로 `press_guard/predict.py --input press_submission/data/3_소성가공_예지보전/outlier_data.csv --out <임시>/predict_cli.csv --cases <임시>/cases_cli.csv --chunk 128`을 실행했다. 출력 비교는 행/열·숫자·문자열·경보를 별도로 대조했다. 정확한 임시 경로는 `judge06_venv_path.json`에 있다.

이번 평가관은 E1 전체 약 8분 실행, E2 전체 실행, E3 전체 184설정 실행을 중복하지 않았다. E2 내용·재실행은 모델 평가관, E3 독립 재집계·부분 재학습은 총괄 평가관이 담당하며, 그 결과를 이 평가관의 직접 수행으로 계산하지 않았다. LSTM 캐시 없는 전체 재학습·다른 OS·새 실제 날짜/설비 데이터 검증도 이번 직접 수행 범위 밖이다. v2 새 클론의 기준모델/LSTM 비교표는 커밋된 표를 해시 검증해 재사용한다.

정상/이상 날짜 교락, 독립 고장/정비 이력 부족은 데이터의 외생적 한계이며 실행 재현 버그와 구분한다. 보고서·발표자료·최종 ZIP 미조립은 사용자 지시에 따른 보류로서 감점 사유로 세지 않았다. 기존 소스·기존 결과·동결 기대값은 수정하지 않았고 Git commit/push를 하지 않았다.
