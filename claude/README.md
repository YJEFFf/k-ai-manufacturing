# claude/ — 준용 × Claude 분석 작업

제6회 K-인공지능 제조데이터 분석 경진대회(일반국민/대학(원)생) 준비 중 Claude Code로 진행한 분석입니다.
예준님(Codex) 작업과 섞이지 않게 이 폴더에만 둡니다.

> **제출 파이프라인 (③ 프레스):** `python code/press/pipeline/run_all.py` 한 번 → 모델 비교·예측 파일·오류분석·진단 ([`code/press/pipeline/README.md`](code/press/pipeline/README.md)). 보고서용 수치: [`notes/프레스_결과요약_보고서용.md`](notes/프레스_결과요약_보고서용.md)
>
> **먼저 읽을 것 (③ 프레스, 9/23~):** [`notes/프레스_분석방향_아이디어.md`](notes/프레스_분석방향_아이디어.md) — 분석 방향, 수상작·논문 조사, 아래 검증 결과 전부.
> 용접 시기(9/22) 기록: [`notes/HANDOFF_2026-09-22.md`](notes/HANDOFF_2026-09-22.md)

## 핵심 발견 (③ 프레스, 2026-09-23)

예준 `codex/analysis/press_welding_review/press_policy_audit.py` 틀(분할·예산·분모·집계 함수)을 **import 해서 그대로** 쓰고 모델만 추가했습니다. 기존 3모델 수치는 예준 결과와 완전히 같습니다.

1. **형식 누수 2개** (`05_requantize_audit.py`) — 이상 파일 전류값은 100% 1.1920929 격자 위(규칙 F1 0.972), 진동은 정상 소수 6자리 vs 이상 8~10자리(규칙 **F1 1.000**). 두 날 모두 같은 양자화로 반올림하면 규칙은 무너지고 **max-z·5NN·RMS 성능은 36설정 전부 그대로**(F1 차이 ≤0.005) → 예준 결과는 형식 누수로 부풀지 않음.
2. **전류 사인파 붕괴** (`06_alias_frequency_audit.py`) — 10Hz로 찍힌 60Hz 전류는 정상 530구간 전부 사인 피팅 R² 0.993~1.000(앨리어싱 0.600±0.002Hz), 이상 17구간은 R² 0.29~0.78. max-z가 놓치는 3구간(진동이 정상 수준)을 이 규칙이 잡음.
3. **max-z + 사인 R² 결합** (`07_policy_with_sine.py`) — 두 점수를 정상 학습 ECDF 꼬리확률로 바꿔 최댓값, 문턱 1개(오경보 예산 합산). **두 분할 × 행/구간 보정 × 1·3·5% 12설정 전부 이상 21/21**(기존 최대 19/21), 전체 행 F1 0.55~0.64 → 0.91~0.92. 정상 알림 구간은 60/20/20 1%에서 0/120, 50/20/30 1%에서 6/180(max-z 3/180).
4. **창 길이 민감도** — 5~10관측에서 24셀 전부 21/21. 12 이상은 max-z가 놓친 구간(길이 10·15)보다 창이 길어져 구조적으로 하락.

⚠️ 한계: 창 길이는 이상 데이터를 본 뒤 정한 탐색 결과. 사인파 붕괴가 고장인지 이상일의 수집 설정 차이인지 분리 불가(이상일은 저장 형식도 달랐음). 두 분할은 같은 이상 600행 재사용.

## 폴더

| 경로 | 내용 |
|---|---|
| `notes/HANDOFF_2026-09-22.md` | 전체 요약 · 미완 작업 · 5회 본선 명단 분석 |
| `notes/데이터셋_구성.md` | 5개 데이터셋 실사 |
| `notes/주제추천_수상가능성.md` | 수상가능성 기준 주제 비교 |
| `notes/용접_수상전략.md` | ② 용접 전략 (진단 D1~D10, 평가항목별 설계) |
| `notes/문의메일_초안.md` | 주최 측 문의 메일 (발송용 C 버전) |
| `notes/프레스_분석방향_아이디어.md` | ③ 프레스 분석 방향 · 수상작/논문 조사 · 05~07 검증 결과 |
| `code/press/pipeline/` | ③ 프레스 **제출 파이프라인** (`run_all.py`) |
| `code/press/` | ③ 프레스 탐색 스크립트 05~07 (결과는 `code/press/outputs/`, 큰 CSV 제외) |
| `notes/프레스_결과요약_보고서용.md` | 보고서 장별 수치·문장 |
| `notes/프레스_실행계획_2026-09-23.md` | 파이프라인 계획 (Architect·Critic 리뷰 3회 반영) |
| `code/` | ② 용접 분석 파이프라인 (01~04 + 공통 모듈 `wlib.py`) |
| `code/outputs/` | 실행 결과 보고서(`*_report.md`)·그림·요약. 큰 CSV는 제외(재실행하면 생김) |
| `data/` | 원본 데이터 자리 (git에 올리지 않음) |

> 노트는 Obsidian 볼트에서 옮겨 와 `[[링크]]` 표기가 남아 있습니다. 같은 폴더의 같은 이름 파일을 가리킵니다.

## 핵심 발견 (② 용접, 9/22)

- **원본은 2,177행(18.2%)뿐.** 3/24 전체와 3/25 앞부분만 원본이고, 나머지 7일은 이 구간을 이어 붙인 복제입니다. 셀값 1,001행 완전 일치, 행 순서 셔플 귀무실험 0%, GitHub 공개 사본과 SHA-256 동일 → KAMP 공개본 자체가 이렇습니다.
- 라벨은 일별 × 유형별 불량 **개수**(23행, 총 39건)뿐이라 건별 연결이 안 됩니다.
- **무작위 행 분할이면 평가 행의 96.7%가 학습과 같은 원본** → 원본 구간 단위 분할(`wlib.make_folds`)로 누수 0%.
- 베이스라인(SPC·IsolationForest·AutoEncoder·Mahalanobis)의 상위 1% 경보는 고가압력 블록(전체의 8%)이나 고전류 스테퍼 구간에 몰림 → 불량이 아니라 '운전 조건 변화'를 잡습니다.
- 가상 불량 주입 벤치마크(시뮬레이션): **국소 잔차(Ctx) 방식이 F1 0.305**(고가압력 블록 밖 0.484)로 최고. 물리 특징(입열량·저항)은 탐지력을 더하지 못함 → 해석용.
- 3/25 원본에서 전류 스테퍼 상승 → 리셋 주기(69·109·99·69용접, 전극 팁 드레싱 후보) 발견.

## 실행

**③ 프레스** — `data/3_소성가공_예지보전/`에 `press_data_normal.csv`, `outlier_data.csv`를 넣는다. 레포 루트의 `codex/` 스크립트를 자동으로 찾는다.

```bash
cd claude
python code/press/05_requantize_audit.py     # 형식 누수 + 재양자화 후 예준 틀 재실행   (~1분)
python code/press/06_alias_frequency_audit.py # 구간 사인 피팅 · 조기판정              (~1분)
python code/press/07_policy_with_sine.py      # 예준 틀 + 사인 모델, 두 분할           (~1분)
python code/press/07_policy_with_sine.py --wins 5 6 8 10 12 15 20 --out code/press/outputs/policy_sine_windows  # 창 길이 민감도
```

**② 용접**

```bash
cd claude
pip install -r code/requirements.txt
# data/2_용접기/ 에 'Welding Data Set_01.xlsx', 'scaled_data.csv' 를 넣는다 (data/README.md 참고)
python code/01_diagnose_welding.py      # 진단 (D1~D10)
python code/02_physics_lobe.py          # 물리 특징 · 경험적 로브 · 스테퍼
python code/03_baselines.py             # 베이스라인 4종 + 누수 점검 + 일별 LODO   (~30초)
python code/04_injection_benchmark.py   # 가상 불량 주입 벤치마크                 (~2분)
```

## 주제 상태

2026-09-23 예준 판단으로 **③ 프레스**로 전환 (레포 루트 README). 용접 자료는 기록으로 남겨 둡니다.
