# 가이드북 LSTM 오토인코더 보완 실험 (프레스 ③)

2026-10-07, Claude Code. 사전 등록은 [PROTOCOL.md](PROTOCOL.md)에 있다.

## 무엇을 왜 했나

- **질문:** 가이드북 모델(LSTM 오토인코더)을 보고서와 같은 조건에서 할 수 있는 만큼 보완하면 어디까지 오르나? 그 결과는 우리 모델 v2·v2+R1·v2+R1+R2와 비교하면 어떤가?
- **전제:** 결과가 좋으면 모델을 바꿀 수도 있다(예준 지시). 그래서 어느 쪽이 낫다는 가정 없이 진행했다.
  - 변형 격자·선택 규칙·해석 기준을 실행 전에 고정했다.
  - valid로만 골랐고, 잠근 뒤에 test를 열었다.
- **같은 조건:** 준용 tvt 코드(`claude/code/press/tvt`)를 import만 해서 그대로 썼다. `claude/`에는 아무것도 쓰지 않았다. 쓴 것은 다음과 같다.
  - 분할 A·B
  - 형식 누수 제거
  - v2 표준화
  - conformal 보정(valid 정상 기록별 최대 점수, valid 정상 행 LOO)
  - 실시간 행 채점과 R1

## 결과

(실행 뒤 채운다)

## 파일

| 파일 | 내용 |
|---|---|
| `PROTOCOL.md` | 사전 등록: 격자, 선택 규칙, 보고 항목, 해석 기준, 실행 전 예상 |
| `lx_harness.py` | 준용 tvt 모듈을 import만 하는 공통 부분: 행 표, 보정, 채점 |
| `lx_lstm.py` | LSTM 오토인코더 변형: 예준 `lstm_ae.py` 구조·학습 루프에 창·앞부분 처리·용량·예산만 바꿀 수 있게 함 |
| `lx_scoring.py` | 채점 방식: 시간 요약 × 채널 처리 |
| `00_reproduce.py` | 준용 tvt 결과 재현 |
| `01_train.py` | 변형 학습. 1단계 격자, 2단계 용량·예산 |
| `02_valid_select.py` | valid 채점과 사전 규칙에 따른 선택, 잠금 |
| `03_test.py` | 잠금 확인 뒤 test 채점과 주 비교 |
| `04_conditions.py` | 운전 상태별 오경보, 미탐 위치, 첫 경보 지연 |
| `05_robustness.py` | 인공 주입·교락 시험(V1·V1b·V2·V5)을 우리 모델과 같은 주입으로 |
| `outputs/` | 작은 결과 표(CSV·JSON) |
| `cache/` | 행 표·학습 결과·가중치. Git 제외, 다시 만들 수 있음 |

## 다시 실행

`yejun/analysis/press_lstm_improvement`에서 아래 순서로 실행한다. `PYTHONDONTWRITEBYTECODE=1`을 붙여 `claude/`에 바이트코드가 생기지 않게 한다. 환경은 Python 3.12.2, torch 2.5.1, pandas 2.3.3, numpy 1.26.4이고 Apple M2 8코어에서 돌렸다.

```
PYTHONDONTWRITEBYTECODE=1 python3 00_reproduce.py
PYTHONDONTWRITEBYTECODE=1 python3 01_train.py --stage 1 --workers 7
PYTHONDONTWRITEBYTECODE=1 python3 02_valid_select.py --stage 1
PYTHONDONTWRITEBYTECODE=1 python3 01_train.py --stage 2 --workers 7      # 용량
PYTHONDONTWRITEBYTECODE=1 python3 02_valid_select.py --stage 2a
PYTHONDONTWRITEBYTECODE=1 python3 01_train.py --stage 2 --workers 7      # 학습 예산 (2a 선택 파일이 있으면)
PYTHONDONTWRITEBYTECODE=1 python3 02_valid_select.py --stage final        # 잠금
PYTHONDONTWRITEBYTECODE=1 python3 03_test.py
PYTHONDONTWRITEBYTECODE=1 python3 04_conditions.py
PYTHONDONTWRITEBYTECODE=1 python3 05_robustness.py --workers 7
```

LSTM 학습은 PC(플랫폼)마다 결과가 조금씩 다르다. 같은 PC에서는 같은 시드로 다시 학습하면 비트 단위로 같은 결과가 나온다(05에서 확인). 그래서 시드 3개로 잰다.
