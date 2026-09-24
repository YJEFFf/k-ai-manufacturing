# 출처와 변경점

이 패키지는 팀 저장소의 기존 코드를 읽기 전용으로 참조해 다시 작성했다. 원본은 수정하지 않았다. 해시는 파일 내용 SHA-256 앞 16자리, 커밋은 그 파일의 마지막 변경 커밋이다.

| 원본 | 커밋 | sha256 | 이 패키지에서 |
|---|---|---|---|
| `yejun/analysis/press_welding_review/press_policy_audit.py` (예준 평가 헬퍼) | 320818e | 4887e4c52bcb9022 | `vendor/press_policy_audit.py`로 바이트 동일 복사. `blocks, rms5, cutoff_at_budget, segment_max, summarize_records, SPLITS, BUDGETS` 사용. import 시 LF 정규화 해시 검증 |
| `claude/code/press/pipeline/data.py` (준용) | cee2267 | f95f3e1fddeeb8f6 | `press/data.py`로 재작성: 해시·행 수 검증, 행 상태(bad_timestamp/bad_value), 잘못된 행 경계, 분할 A/B 이름, 전처리 3종 통합 |
| `claude/code/press/pipeline/scores.py` (준용) | bfe9290 | 230cf028f9ae6901 | 2단계에서 `press/scores.py`로 재작성 예정(사인 적합 hat 행렬·max-z·5NN·RMS5·IF·MLP-AE 구조 재사용, 상한 있는 `tail_logp`는 q95 지수 꼬리로 대체) |
| `claude/code/press/pipeline/evaluate.py` (준용) | bfe9290 | 0cd565da0062deb6 | 2단계에서 `press/calibrate.py`·`press/evaluate.py`로 재작성 예정(conformal p, criterion 열, alpha_grid) |
| `claude/code/press/pipeline/diagnosis.py` (준용) | bfe9290 | 828b70771a173d10 | `press/diagnosis.py`로 재작성: 자릿수·격자 허용오차 2종·규칙 발화율/AUROC·Δt 분해·구간 평균 범위·lag-1 자기상관·파형 표 추가. '지터'·DC 오프셋 해석 제거 |
| `claude/code/press/pipeline/analysis.py` (준용) | bfe9290 | d79e94d51a93a13b | 3단계에서 `press/analysis.py`로 재작성 예정(분모 포함 조건표·2×2 상호작용) |
| `claude/code/press/pipeline/select_w.py` (준용) | bfe9290 | 418a8c71185794c8 | 사용하지 않음(PLAN §2: 주 모델 w=8 고정, 민감도 공개) |
| `claude/code/press/pipeline/run_all.py` (준용) | bfe9290 | 3e54190db9347cd1 | `run_all.py`로 재작성: 한 `--root/--out`, manifest·checks, 원값 열 검사, artifact 계약 |
| `claude/code/press/05_requantize_audit.py` (준용) | 41f4ab6 | 20180b051acc1343 | `quantize()`와 형식 규칙 정의를 `press/data.py`·`press/diagnosis.py`에 재구현(간격 1.1920929, 잔차 허용오차 1e-3 기존값 유지 + 1e-6 병기) |
| `claude/code/press/06_alias_frequency_audit.py` (준용) | 41f4ab6 | 97b565836f552558 | 구간 사인 적합(0~5Hz·0.005Hz 격자)을 `press/diagnosis.py`에 재구현(hat 행렬로 벡터화) |
| `yejun/analysis/press_merge_review/review_checks.py` (예준) | 미커밋 | — | 재양자화·포화·경로 검사 아이디어를 3단계 `press/robustness.py`에 반영 예정 |

기록구간 규칙은 `press.data.segments` 하나만 사용하며 vendor `blocks`와의 일치를 `run_all.py`와 `tests/`에서 확인한다.
