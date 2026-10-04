"""가이드북 LSTM-Autoencoder 재현 베이스라인 (분석실습 가이드북 27~41쪽, 코드 14·19~31).

목적: 주최 측 가이드의 LSTM-AE를 파이프라인의 같은 평가 틀(예준 분할, 정상 보정 구간 conformal 문턱)에 넣어
    최종 모델 fused_acat과 비교할 기준선을 만든다. 결론은 '2분 예산(25 epoch) LSTM-AE 기준'으로 한정한다.
방법 (가이드 TensorFlow 코드를 PyTorch로 같은 구조로):
- 전처리: 센서 3열 절댓값(가이드 코드 14는 use_col 전체에 적용 → 전류도 절댓값) → MinMaxScaler, 학습 구간으로만 fit
- 창 20행(2초). 점수 = 창 마지막 시점 복원값의 MSE(3변수 평균, 가이드 flatten), 창의 마지막 행에 붙인다.
  가이드의 "+100시점 뒤 라벨"은 라벨 정렬용이라 쓰지 않는다
- 층: LSTM(64) → LSTM(32) → RepeatVector(20) → LSTM(32) → LSTM(64) → TimeDistributed(Dense(3)), Keras 기본 초기화
- 학습: 손실 MSE, Adam(1e-3), batch 128, ReduceLROnPlateau(0.7, 50), EarlyStopping(120, 1e-5, 최적 가중치 복원).
  25 epoch에서는 학습률 감소(patience 50)와 조기종료(patience 120)가 한 번도 작동하지 않고 최적 가중치 복원만 작동한다
  (lstm_ae_train_log.csv의 lr 열이 끝까지 1e-3)
- 검증 = 학습 구간의 마지막 10% 기록구간. 이 구간은 학습 창에서도 빠지므로 학습 창은 학습 구간의 앞 90%뿐이다.
  가이드는 학습 구간 전체로 학습하고 평가 정상의 앞 880창으로 검증한다 — 보정·평가 구간을 건드리지 않으려고 바꿈
- epoch: 가이드 최대 800(수렴 200~300)이지만 분할당 두 모델 학습을 2분 예산에 넣으려고 25로 줄였다. 25 epoch 시점에도
  두 분할·두 모델 모두 정상 검증 손실이 내려가는 중이다(과소학습, 최적 epoch 24~25). 이상 데이터는 보지 않았다
- 변형 셋 (학습은 guide·segment 두 번):
  lstm_ae_guide          = 기록 공백을 무시하고 프레임 행 순서로 20행 창 (가이드 방식, 프레임 앞 19행만 NaN).
                           정상 데이터에서 창의 약 절반이 기록 공백을 넘는다
  lstm_ae_guide_noncross = guide 모델 점수에서 공백을 넘는 창(창 첫 행과 끝 행의 기록구간이 다름)의 점수를 NaN으로 둔 것.
                           재학습 없음. 채점 행이 segment와 같아 guide 결과 중 공백 넘는 창의 몫을 가른다
  lstm_ae_segment        = 기록구간 안 창으로만 학습·채점. 20관측 미만 구간 전체(정상 행 약 7%, 이상 21구간 중 8개)와
                           각 구간 앞 19관측이 채점되지 않아 정상 행 약 50%, 이상 행 54%가 점수 없음 (noncross도 같다)
- 문턱은 가이드의 PR 곡선 교차점(이상 라벨 사용) 대신 evaluate()의 conformal 문턱. 이상 데이터는 평가에만 쓴다
- ap_scored_rows는 점수가 있는 행에서만 계산해 변형마다 모집단이 다르다. 그래서 ap_scored_row_fraction
  (평가 정상+이상 행 중 채점 행 비율)을 옆 열에 싣는다. guide ≈ 0.99, segment·noncross ≈ 0.50, 이 비율이 다른 AP끼리 비교하지 않는다
- 재현: OMP_NUM_THREADS=1은 모듈 상단 setdefault(run_all·perturb와 같다). torch 시드·1스레드·결정 알고리즘은 fit 안에서만
  켜고 끝나면 되돌린다. 실행마다 달라지는 학습 시간(train_seconds)은 lstm_ae_train_log.csv(epoch별 손실·학습률·경과 초)에만
  쓰므로 lstm_ae_metrics.csv는 재실행해도 바이트 단위로 같다
한계:
- 25 epoch은 2분 예산으로 정한 값이고 과소학습이다. 검토 재실행(60_20_20)에서 guide를 100 epoch 학습하면 검증 손실
  0.0169 → 0.0124, 기록구간 conformal 1% 기준 이상 19/21·정상 0/120·F1 0.63(25 epoch은 17/21·F1 0.40)이었다.
  최종 모델보다 약하다는 방향은 같지만(F1 0.63 대 0.94) 격차의 크기는 대부분 epoch 예산에서 생긴다
- epoch 곡선을 본 검증 블록(60_20_20 학습 구간의 마지막 10%, 블록 323~359)은 50_20_30 분할의 보정 구간(블록 300~419)에
  속한다. 정상 데이터이고 라벨도 안 썼으니 이상 누출은 아니지만, 두 번째 분할의 보정 블록이 설정 선택에 쓰였다
- 기록 공백은 수 초다(정상 0~16.6초·중앙값 4.2초, 최대 약 17초. 이상 1.8~8.6초). 이상 파일은 21구간이 2.8분 안에 붙어 있어
  guide의 짧은 이상 구간 경보는 대부분 앞 이상 구간 행이 섞인 창에서 넘어온다. 1% 기준 guide 17구간 중 9구간은 (두 분할 모두)
  공백을 넘는 창으로만 잡혔다. 공백 넘는 창을 뺀 guide_noncross(1/3/5%: 60_20_20 8/12/12, 50_20_30 10/11/12)는
  segment(8/11/12, 10/11/13)와 거의 같다. guide와 segment의 차이를 모델 능력 차이로 읽지 않는다
- 주 결과는 기록구간 단위 보정이다. 행 단위 보정에서는 guide가 18~20구간을 잡지만 정상 알림 구간도 5~41개로 는다
- 전류 절댓값은 사인 부호 정보를 버린다. 시드 하나(0)만 돌렸다
"""
import contextlib
import copy
import os
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # torch·BLAS 수치 재현 (run_all·perturb와 같다)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
from sklearn.preprocessing import MinMaxScaler  # noqa: E402
from torch import nn  # noqa: E402

from data import DEFAULT_ROOT, SENSORS, load, load_vendor, split_sets  # noqa: E402
from evaluate import evaluate  # noqa: E402
from scores import _window_index  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "pipeline"
SEQ = 20
EPOCHS = 25  # 2분 예산. 두 분할 모두 25 epoch에도 정상 검증 손실 하강 중(과소학습) — docstring 한계 참고
BATCH = 128
LR = 1e-3
VAL_FRAC = 0.1
SEED = 0
MODELS = {"lstm_ae_guide": False, "lstm_ae_segment": True}  # 학습하는 모델: 기록구간 안 창만 쓰는지
NONCROSS = {"lstm_ae_guide_noncross": "lstm_ae_guide"}  # 파생 변형: 원 모델 점수에서 공백 넘는 창만 NaN


@contextlib.contextmanager
def _torch_determinism():
    """fit 동안만 torch 시드·1스레드·결정 알고리즘. 끝나면 전역 RNG 상태와 설정을 되돌린다."""
    threads = torch.get_num_threads()
    det, warn = torch.are_deterministic_algorithms_enabled(), torch.is_deterministic_algorithms_warn_only_enabled()
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(SEED)
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        try:
            yield
        finally:
            torch.set_num_threads(threads)
            torch.use_deterministic_algorithms(det, warn_only=warn)


class LSTMAE(nn.Module):
    def __init__(self, n=len(SENSORS), seq=SEQ):
        super().__init__()
        self.seq = seq
        sizes = [(n, 64), (64, 32), (32, 32), (32, 64)]  # 인코더 2층, 디코더 2층
        self.lstms = nn.ModuleList([nn.LSTM(i, h, batch_first=True) for i, h in sizes])
        self.out = nn.Linear(64, n)
        # Keras 기본값: 입력 가중치 glorot_uniform, 순환 가중치 orthogonal, 편향 0 (망각 게이트만 1)
        for m in self.lstms:
            nn.init.xavier_uniform_(m.weight_ih_l0)
            nn.init.orthogonal_(m.weight_hh_l0)
            nn.init.zeros_(m.bias_ih_l0)
            nn.init.zeros_(m.bias_hh_l0)
            with torch.no_grad():
                m.bias_ih_l0[m.hidden_size:2 * m.hidden_size] = 1.0
        nn.init.xavier_uniform_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, x):
        e1, e2, d1, d2 = self.lstms
        _, (h, _) = e2(e1(x)[0])
        h = h[-1].unsqueeze(1).repeat(1, self.seq, 1)  # RepeatVector
        return self.out(d2(d1(h)[0])[0])


def _prep(scaler, frame):
    return scaler.transform(np.abs(frame[SENSORS].to_numpy(float)))


def _windows(z, groups, segment):
    """(창 끝 행 번호, 창 (n, SEQ, 3)). segment=False면 기록구간 경계를 무시한다 (가이드)."""
    idx = _window_index(groups, SEQ) if segment else np.arange(SEQ - 1, len(z))
    X = np.stack([z[i - SEQ + 1:i + 1] for i in idx]) if len(idx) else np.empty((0, SEQ, z.shape[1]))
    return idx, torch.from_numpy(X.astype(np.float32))


@torch.no_grad()
def _last_err(model, X):
    """창 마지막 시점 복원 오차 (가이드 flatten + 변수 평균 MSE)."""
    model.eval()
    out = [((model(X[b:b + 4096])[:, -1] - X[b:b + 4096, -1]) ** 2).mean(1) for b in range(0, len(X), 4096)]
    return torch.cat(out).numpy().astype(float) if out else np.empty(0)


@torch.no_grad()
def _loss(model, X):
    model.eval()
    return float(sum(((model(X[b:b + 4096]) - X[b:b + 4096]) ** 2).sum() for b in range(0, len(X), 4096)) / X.numel())


def fit(train, blocks, segment):
    """정상 학습 구간으로 스케일러·모델 적합. 반환: (model, scaler, 학습 정보 dict).
    학습 정보의 history는 epoch별 dict(train_loss, val_loss, lr, train_seconds=fit 시작부터 경과 초)."""
    t0 = time.perf_counter()
    with _torch_determinism():
        g = blocks(train)
        scaler = MinMaxScaler().fit(np.abs(train[SENSORS].to_numpy(float)))
        z = _prep(scaler, train)
        cut = int(np.flatnonzero(g >= int(round(g.max() * (1 - VAL_FRAC))))[0])  # 검증 = 마지막 10% 기록구간
        _, Xt = _windows(z[:cut], g[:cut], segment)  # 학습 창 = 학습 구간 앞 90%
        _, Xv = _windows(z[cut:], g[cut:], segment)
        model = LSTMAE()
        opt = torch.optim.Adam(model.parameters(), lr=LR, eps=1e-7)  # Keras epsilon
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.7, patience=50, threshold=1e-4,
                                                           threshold_mode="abs")
        gen = torch.Generator().manual_seed(SEED)
        best, best_ep, state, wait, hist = np.inf, -1, None, 0, []
        for ep in range(EPOCHS):
            model.train()
            perm = torch.randperm(len(Xt), generator=gen)
            tot = 0.0
            for b in range(0, len(Xt), BATCH):
                xb = Xt[perm[b:b + BATCH]]
                opt.zero_grad()
                loss = ((model(xb) - xb) ** 2).mean()
                loss.backward()
                opt.step()
                tot += loss.item() * len(xb)
            val = _loss(model, Xv)
            sched.step(val)  # 25 epoch에서는 patience 50에 닿지 않아 학습률이 그대로다
            hist.append(dict(train_loss=tot / len(Xt), val_loss=val, lr=opt.param_groups[0]["lr"],
                             train_seconds=time.perf_counter() - t0))
            if val < best - 1e-5:
                best, best_ep, state, wait = val, ep, copy.deepcopy(model.state_dict()), 0
            else:
                wait += 1
                if wait >= 120:  # 25 epoch에서는 작동하지 않는다
                    break
        model.load_state_dict(state)  # restore_best_weights
    info = dict(train_windows=len(Xt), val_windows=len(Xv), epochs_run=len(hist), best_epoch=best_ep + 1,
                train_loss_last=hist[-1]["train_loss"], val_loss_best=best, history=hist)
    return model, scaler, info


def score(model, scaler, frame, blocks, segment):
    """행별 점수: 창 마지막 시점 재구성 MSE를 창의 마지막 행에. 창이 없는 행은 NaN."""
    idx, X = _windows(_prep(scaler, frame), blocks(frame), segment)
    out = np.full(len(frame), np.nan)
    out[idx] = _last_err(model, X)
    return out


def noncross(s, groups):
    """점수에서 기록 공백을 넘는 창(창 첫 행과 끝 행의 기록구간이 다름)의 값을 NaN으로. 남는 행 = segment 채점 행."""
    out = np.full(len(s), np.nan)
    keep = _window_index(groups, SEQ)
    out[keep] = s[keep]
    return out


def lstm_models(train, sets, blocks, info=None):
    """{name: (cal, test, abn) 점수}. 학습 모델(MODELS)과 파생 변형(NONCROSS). info에 dict를 주면 학습 정보를 채운다."""
    res = {}
    for name, segment in MODELS.items():
        model, scaler, inf = fit(train, blocks, segment)
        res[name] = tuple(score(model, scaler, d, blocks, segment) for d in sets)
        if info is not None:
            info[name] = inf
    for name, src in NONCROSS.items():
        res[name] = tuple(noncross(s, blocks(d)) for s, d in zip(res[src], sets))
    order = ["lstm_ae_guide", *NONCROSS, "lstm_ae_segment"]
    return {k: res[k] for k in order}


def run(out: Path, root, yj):
    normal, abnormal = load(root)
    rows, log = [], []
    for split, train_end, cal_end in yj.SPLITS:
        train, cal, test = split_sets(normal, yj, train_end, cal_end)
        info = {}
        scores = lstm_models(train, (cal, test, abnormal), yj.blocks, info)
        m, _ = evaluate(yj, split, (cal, test, abnormal), scores)
        for k, v in info.items():
            hist = v.pop("history")
            log += [dict(split=split, model=k, epoch=e + 1, **h) for e, h in enumerate(hist)]
            print(f"{split} {k}: " + ", ".join(f"{a}={b:.4g}" if isinstance(b, float) else f"{a}={b}"
                                              for a, b in v.items())
                  + f", train_seconds={hist[-1]['train_seconds']:.1f}", flush=True)
        for r in m:
            fit_model = NONCROSS.get(r["model"], r["model"])
            r["ap_scored_row_fraction"] = ((r["normal_scored_rows"] + r["abnormal_scored_rows"])
                                           / (r["normal_rows"] + r["abnormal_rows"]))
            r.update(fit_model=fit_model, **info[fit_model])
        rows += m
    df = pd.DataFrame(rows)
    cols = list(df.columns)
    cols.insert(cols.index("ap_scored_rows") + 1, cols.pop(cols.index("ap_scored_row_fraction")))
    df = df[cols]
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "lstm_ae_metrics.csv", index=False)  # 결정적 값만 → 재실행 시 바이트 동일
    pd.DataFrame(log).to_csv(out / "lstm_ae_train_log.csv", index=False)  # 학습 시간 등 실행마다 달라지는 값
    return df


if __name__ == "__main__":
    t = time.perf_counter()
    d = run(OUT, DEFAULT_ROOT, load_vendor())
    main = d[(d.rule == "conformal") & (d.calibration_unit == "recording_segments")]
    print(main[["split", "model", "budget", "abnormal_notified_segments", "normal_notified_segments",
                "normal_recording_segments", "f1_all_rows", "ap_scored_rows", "ap_scored_row_fraction"]]
          .to_string(index=False))
    print(f"total {time.perf_counter() - t:.1f}s")
