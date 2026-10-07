# 제출 코드 통합 빌더

기존 제출 ZIP과 정상 전용 개선 실험을 저장소 없이 실행할 수 있는 하나의 패키지로 묶는다. 기존 `claude/submission/북적북적_code.zip`, 원자료, 실험 잠금 모듈은 변경하지 않는다.

```console
python -X utf8 yejun/submission/press_integrated_2026-10-08/build_package.py --include-extra-audits
```

완성 ZIP은 이 폴더의 `북적북적_code_통합본.zip`이다. `build_result.json`에 ZIP 해시와 빌드 위치를 남긴다. ZIP과 빌드 디렉터리는 원자료를 포함하므로 Git에서는 제외한다. `templates/`에는 단일 실행 진입점, 공통 환경, 배포 무결성 검사와 재계산 대조 스크립트가 있다. 독립 환경에서 압축을 풀고 `pip install -r requirements.txt`, `python run_all.py`를 실행하면 된다.

`--include-extra-audits`는 같은 조건의 강한 대조군·정상 조건 민감도 검사를 포함한다. 배포본의 `run_all.py --extra-audits`가 이를 후속 단계로 실행한다. 추가 검사의 결과는 기존 선택·보정값을 바꾸지 않는다.

원래 실행기를 `run_official.py`로 보존하고 공식 26단계와 기존 기대값 계약을 그대로 실행한다. 공식 05 모듈에서는 사용하지 않는 익명 비교 메타데이터 키워드 하나만 제거하고 나머지 AST가 같은지 확인한다. 원래 예측 사본은 `reference_results/official_predictions/`로 옮겨 놓고 새 `predictions/`는 실행으로 생성한다. 학습 캐시·가중치를 넣지 않으며, 개선 실험의 `outputs/`도 비어 있는 상태에서 시작한다.

배포 문서에는 실행과 검증에 필요한 내용만 담는다. 선택 대상이 아니었던 비교기 3개를 코드·격자·검사·기준표에서 제외하고, 남은 단독 8개와 결합 48개 및 별도 OR 4개의 계산 AST가 원본과 같은지 확인한다. 원래 선택 잠금의 소스·설정·선정 표 해시를 먼저 검사하고, 배포 기준표 잠금에는 실제 포장 시각과 역사적 선택 시각을 따로 쓴다. 원래 잠금 SHA-256도 연결한다. 기준표는 원래 표의 해당 모델 행만 제거한 값이며, 실제 선택과 평가를 정상 전용 개발 단계부터 다시 실행해 같은 결과인지 확인한다. `reference_results/improvement/`의 표는 실행 결과를 대신하지 않는다.

검증 범위와 새 데이터 평가 절차는 ZIP 안의 `README.md`를 따른다. 빌더 경로 탈출·학습 캐시 거부·계산 변경 감지 검사는 `test_package_builder.py`에 있다. 완전한 새 환경에서 수행한 최종 검증 기록은 `verification/`에 별도로 남긴다.

검증 완료 기록은 [clean_run.json](verification/clean_run.json)에 있다. 공통 Python 3.14.7 새 가상환경과 저장소 밖 세 압축 해제 폴더에서 기존 26단계(43/43 대조, 3,709.66초), 비교기 제거 후 개선 실험 7단계(522.84초), 최종 ZIP 추가 감사 5단계(375.52초)를 실행했다. 마지막 실행에서 계약 검사 108개가 통과했고, 추가 감사 CSV 15개·1,598행도 별도 로컬 실행과 일치했다. 빌더 불변·음성 검사는 별도로 6개 통과했다.

초기 공식 실행과 비교기 제거 후보의 실행은 소스·자료·기준표·분기 AST 동등 증명으로 최종 ZIP에 연결했다. 공식 모듈의 유일한 계산 외 차이는 사용하지 않는 메타데이터 키워드 1개 제거다. 최종 추가 감사는 검증한 기본 결과의 해시를 확인한 뒤 복사하고 새로 계산했다. 하나의 압축 해제 폴더에서 `--section all`을 연속 수행한 기록은 아니다. `verify_clean_package.py`, `compare_extra_audits.py`, `consolidate_verification.py`가 실행 및 증거 대조를 수행하며 Python 파일 접근 차단은 OS 수준 격리와 구분한다.

최종 ZIP SHA-256은 `2bee634dc651368b5b11787c7e97b1a61b2b7e4ea2a6de8a059245536f4d4ed7`이다. VD3 별도 수식 19,104행에서 경보 차이 0, 고정 상태의 기존 시험 11,387행에서도 경보가 모두 일치했다. 추가 고장 자료가 없어 새 사건의 독립 성능 검증은 하지 않았다. 보고서 원고·HWPX·PDF 3개와 원본 자료 4개의 보존 및 역사적 선택 잠금은 [preserved_sources_and_reports.json](verification/preserved_sources_and_reports.json)에 기록했다.
