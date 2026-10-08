# 제출 코드 통합 빌더

기존 제출 ZIP, 정상 전용 개선 실험, 추가 감사를 저장소 없이 실행할 수 있는 하나의 패키지로 묶는다. 기존 `claude/submission/북적북적_code.zip`, 원자료, 실험 잠금 모듈은 변경하지 않는다. ZIP과 빌드 디렉터리는 원자료를 포함하므로 Git에서 제외한다.

## 2026-10-08 보완판(Claude Code)

배포본에 넣는 것은 다음과 같다(`templates/`, `build_package.py`).

| 구분 | 내용 |
|---|---|
| 설치 없는 확인 | `check_bundled.py`(표준 라이브러리만): 파일 해시, 동봉 예측 파일 해시, 행 F1 재계산 |
| 실행 기본값 | `run_all.py`가 추가 감사까지 기본 실행. `--skip-extra-audits`로 뺀다. 출력은 UTF-8로 고정하고, 새로 푼 폴더에서 `--verify-only`를 주면 안내 후 종료(코드 2) |
| 추가 감사 기준표 | `reference_results/extra_audits/`에 32개 표(개선 15, 공식 산출물 의존 17)를 넣고 `verify_extra.py`로 자동 대조 |
| 추가 분석 | 공식 규칙 상수 민감도(`press_official_sensitivity`), 두 단계 재생·경보량(`press_stage_replay`) |
| 콘솔 | `yejun/press_guard`의 두 단계 콘솔과 화면 파일. 공식 계산이 쓰는 `model.py`·`runtime.py`는 원래 ZIP과 같은지 검사 |

- 실행 기록: 먼저 기록 없는 ZIP(`북적북적_code_통합본_run.zip`)을 만든다. `run_clean_full.py`로 새로 푼 폴더에서 `check_bundled.py`와 `run_all.py`를 끝까지 실행하고 `verification_final/clean_full_run.json`을 남긴다.
- 최종 ZIP: `build_package.py --attach-verification verification_final`로 그 기록을 `verification/`에 넣는다. `verify_attached_build.py`는 실행한 ZIP과 최종 ZIP이 기록 파일·목록 파일 말고는 바이트 단위로 같은지 확인한다.
- 실행 중 PC 절전으로 멈춘 구간은 `verification_final/power_events.json`에 윈도 이벤트 기록으로 남겼다. 이 구간은 실행 기록의 벽시계 시간에 포함된다.

```console
python -X utf8 build_package.py --output 북적북적_code_통합본_run.zip
python -X utf8 run_clean_full.py --archive 북적북적_code_통합본_run.zip --python <새 가상환경 python> --workdir <짧은 임시 경로> --record-dir verification_final
python -X utf8 build_package.py --attach-verification verification_final
python -X utf8 verify_attached_build.py --run 북적북적_code_통합본_run.zip --final 북적북적_code_통합본.zip
```

## 이전 판(Codex)의 구성과 검증

원래 실행기를 `run_official.py`로 보존해 공식 26단계와 기존 기대값 계약을 그대로 실행한다. 공식 05 모듈에서는 사용하지 않는 익명 비교 메타데이터 키워드 하나만 제거하고, 나머지 AST가 같은지 확인한다. 원래 예측 사본은 `reference_results/official_predictions/`로 옮기고, 새 `predictions/`는 실행으로 생성한다. 학습 캐시·가중치는 넣지 않는다.

선택 대상이 아니었던 비교기 3개를 코드·격자·검사·기준표에서 제외한다. 남은 단독 8개, 결합 48개, 별도 OR 4개의 계산 AST가 원본과 같은지 확인한다. 원래 선택 잠금의 소스·설정·선정 표 해시를 먼저 검사한다. 배포 기준표 잠금에는 실제 포장 시각과 역사적 선택 시각을 따로 쓰고, 원래 잠금 SHA-256도 연결한다.

이전 판 ZIP(SHA-256 `2bee634d…`)의 검증 기록은 `verification/clean_run.json`에 있다. 부분별로 새로 푼 세 폴더에서 실행해 연결한 기록이다. 빌더 불변·음성 검사는 `test_package_builder.py`에 있다.
