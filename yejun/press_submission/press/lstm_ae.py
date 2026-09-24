"""W7 LSTM-Autoencoder 세 프로토콜 — PLAN.md §5.1.

1. 가이드북 재구현: abs → MinMax(정상 앞 15,000행) → 공백 무시 창 20, 라벨 100시점 이동(끝 120행 제외) → 검증 880 정상 + 300 이상 창,
   조기 종료·학습률 감소는 검증 정상 창 val_loss 기준 → 마지막 시점 MSE → 검증 PR 곡선의 P=R 점 문턱(이상 라벨 사용) → 평가 4,000 정상 + 180 이상 창.
2. 공통 프로토콜 LSTM20 단독: 주 전처리·정상 학습 표준화, 기록구간 내부 창, 정상 학습 내부(뒤 20% 구간) 조기 종료, 마지막 시점 MSE, 정상 보정만.
3. LSTM20 + max-z 결합: 주 모델과 같은 지수 꼬리·fmax·보정. max-z는 전 행에서 활성화.
PyTorch(CPU, 단일 스레드, 고정 시드)로 구현했으며 원 Keras와 초기화·최적화 세부가 다르다. 가이드북 코드 26은 EarlyStopping(restore_best_weights=True)이며 여기서도 최적 가중치를 복원한다.
학습 결과는 설정·코드·입력·전처리·스케일러를 담은 해시로 캐시한다(검수 R2).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from . import data as D
from .scores import window_index

SEQ = 20
LABEL_SHIFT = 100
GUIDE_TRAIN_ROWS = 15000
GUIDE_VALID_NORMAL, GUIDE_VALID_ANOMALY = 880, 300


class LSTMAE(nn.Module):
    def __init__(self, n_features: int = 3, seq: int = SEQ):
        super().__init__()
        self.seq = seq
        self.e1 = nn.LSTM(n_features, 64, batch_first=True)
        self.e2 = nn.LSTM(64, 32, batch_first=True)
        self.d1 = nn.LSTM(32, 32, batch_first=True)
        self.d2 = nn.LSTM(32, 64, batch_first=True)
        self.out = nn.Linear(64, n_features)

    def forward(self, x):
        h, _ = self.e1(x)
        h, _ = self.e2(h)
        z = h[:, -1:, :].repeat(1, self.seq, 1)
        h, _ = self.d1(z)
        h, _ = self.d2(h)
        return self.out(h)


def code_fingerprint() -> str:
    """학습·점수 계산에 영향을 주는 코드(lstm_ae.py, scores.py, data.py)의 해시. 코드가 바뀌면 캐시가 무효화된다."""
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in ("lstm_ae.py", "scores.py", "data.py"):
        h.update((here / name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def config_key(cfg: dict, code: str | None = None) -> str:
    payload = dict(cfg, code=code if code is not None else code_fingerprint(), protocol_version=D.PROTOCOL_VERSION)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def train_ae(Xtr: np.ndarray, Xval: np.ndarray, epochs: int, patience: int, seed: int = 0, lr: float = 1e-3, batch: int = 128,
             lr_factor: float = 0.7, lr_patience: int = 50, min_delta: float = 1e-5, log=None):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    model = LSTMAE(Xtr.shape[2], Xtr.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=lr_factor, patience=lr_patience)
    loss_fn = nn.MSELoss()
    Xt, Xv = torch.tensor(Xtr, dtype=torch.float32), torch.tensor(Xval, dtype=torch.float32)
    best, best_state, wait, hist = np.inf, None, 0, []
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xt), generator=gen)
        tot = 0.0
        for i in range(0, len(Xt), batch):
            xb = Xt[perm[i:i + batch]]
            opt.zero_grad()
            l = loss_fn(model(xb), xb)
            l.backward()
            opt.step()
            tot += float(l) * len(xb)
        model.eval()
        with torch.no_grad():
            vl = float(loss_fn(model(Xv), Xv))
        sched.step(vl)
        hist.append(dict(epoch=ep + 1, train_loss=tot / len(Xt), val_loss=vl, lr=opt.param_groups[0]["lr"]))
        if vl < best - min_delta:
            best, wait, best_state = vl, 0, {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)   # 가이드북 EarlyStopping(restore_best_weights=True)와 같게 최적 가중치 복원
    model.eval()
    return model, pd.DataFrame(hist)


def last_step_error(model: LSTMAE, W: np.ndarray, batch: int = 2048) -> np.ndarray:
    """가이드북 flatten(): 창의 마지막 시점 재구성 오차(특징 평균)."""
    if len(W) == 0:
        return np.array([])
    out = []
    with torch.no_grad():
        for i in range(0, len(W), batch):
            xb = torch.tensor(W[i:i + batch], dtype=torch.float32)
            xh = model(xb)
            out.append(((xb[:, -1, :] - xh[:, -1, :]) ** 2).mean(1).numpy())
    return np.concatenate(out)


def _cache_get(cache_dir: Path, key: str):
    p = cache_dir / f"{key}.npz"
    if p.exists():
        z = np.load(p, allow_pickle=True)
        return {k: z[k] for k in z.files}
    return None


def _cache_put(cache_dir: Path, key: str, arrays: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez(cache_dir / f"{key}.npz", **arrays)


# ---------- 프로토콜 1: 가이드북 ----------
def protocol_guidebook(normal: pd.DataFrame, abnormal: pd.DataFrame, cache_dir: Path, epochs: int, patience: int, seed: int,
                       input_sha256: dict, retrain: bool = False, log=print) -> tuple[dict, pd.DataFrame]:
    from sklearn.metrics import precision_recall_curve
    from sklearn.preprocessing import MinMaxScaler
    cfg = dict(protocol="guidebook", seq=SEQ, shift=LABEL_SHIFT, train_rows=GUIDE_TRAIN_ROWS, valid=(GUIDE_VALID_NORMAL, GUIDE_VALID_ANOMALY),
               epochs=epochs, patience=patience, seed=seed, torch=torch.__version__, inputs=input_sha256, preprocess="abs+minmax")
    key = config_key(cfg)
    hit = None if retrain else _cache_get(cache_dir, key)
    Xn = np.abs(normal[D.SENSORS].to_numpy(float))
    Xa = np.abs(abnormal[D.SENSORS].to_numpy(float))
    sc = MinMaxScaler().fit(Xn[:GUIDE_TRAIN_ROWS])
    def windows(X):   # 공백 무시, 라벨 100시점 이동 → 끝 seq+100 행 제외
        n = len(X) - SEQ - LABEL_SHIFT
        return np.stack([X[i:i + SEQ] for i in range(n)]) if n > 0 else np.empty((0, SEQ, 3))
    Wtr = windows(sc.transform(Xn[:GUIDE_TRAIN_ROWS]))
    Wtn = windows(sc.transform(Xn[GUIDE_TRAIN_ROWS:]))
    Wa = windows(sc.transform(Xa))
    Wv_n, Wt_n = Wtn[:GUIDE_VALID_NORMAL], Wtn[GUIDE_VALID_NORMAL:]
    Wv_a, Wt_a = Wa[:GUIDE_VALID_ANOMALY], Wa[GUIDE_VALID_ANOMALY:]
    t0 = time.time()
    if hit is None:
        model, hist = train_ae(Wtr, Wv_n, epochs, patience, seed, log=log)
        errs = {k: last_step_error(model, W) for k, W in dict(valid_normal=Wv_n, valid_anomaly=Wv_a, test_normal=Wt_n, test_anomaly=Wt_a).items()}
        _cache_put(cache_dir, key, {**errs, "history": hist.to_records(index=False)})
        train_seconds, epochs_run, cached = time.time() - t0, int(len(hist)), False
    else:
        errs = {k: hit[k] for k in ("valid_normal", "valid_anomaly", "test_normal", "test_anomaly")}
        hist = pd.DataFrame(hit["history"])
        train_seconds, epochs_run, cached = 0.0, int(len(hist)), True
    yv = np.r_[np.zeros(len(errs["valid_normal"]), int), np.ones(len(errs["valid_anomaly"]), int)]
    ev = np.r_[errs["valid_normal"], errs["valid_anomaly"]]
    prec, rec, thr = precision_recall_curve(yv, ev)
    j = int(np.argmin(np.abs(prec[:-1] - rec[:-1])))   # 가이드: P==R인 첫 점(부동소수라 가장 가까운 점)
    threshold = float(thr[j])
    yt = np.r_[np.zeros(len(errs["test_normal"]), int), np.ones(len(errs["test_anomaly"]), int)]
    et = np.r_[errs["test_normal"], errs["test_anomaly"]]
    pred = (et > threshold).astype(int)
    tp, fp = int(((pred == 1) & (yt == 1)).sum()), int(((pred == 1) & (yt == 0)).sum())
    fn, tn = int(((pred == 0) & (yt == 1)).sum()), int(((pred == 0) & (yt == 0)).sum())
    res = dict(protocol="guidebook_reproduction_pytorch", cache_key=key, cached=cached, epochs_run=epochs_run, max_epochs=epochs,
               patience=patience, train_seconds=round(train_seconds, 1), train_windows=int(len(Wtr)),
               valid_windows_normal=int(len(Wv_n)), valid_windows_anomaly=int(len(Wv_a)),
               test_windows_normal=int(len(Wt_n)), test_windows_anomaly=int(len(Wt_a)),
               threshold=threshold, valid_precision=float(prec[j]), valid_recall=float(rec[j]),
               tn=tn, fp=fp, fn=fn, tp=tp, accuracy=(tp + tn) / len(yt), precision=tp / (tp + fp) if tp + fp else 0.0,
               recall=tp / (tp + fn) if tp + fn else 0.0, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0, false_alarm_rate=fp / (fp + tn),
               guide_reported=dict(tn=3922, fp=78, tp=154, fn=26, accuracy=0.9751, f1=0.7476),
               notes="검증셋에 이상 300창이 들어가 문턱 선택에 이상 라벨을 쓴다. 창이 기록 공백을 가로지르며 라벨 100시점 이동은 실제 시간과 다르다. 주 비교표와 다른 프로토콜이다.")
    return res, hist


# ---------- 프로토콜 2·3: 공통 평가 프로토콜 ----------
def protocol_common(train: pd.DataFrame, seg_train: np.ndarray, frames: dict, segs: dict, scaler_mean, scaler_scale,
                    cache_dir: Path, epochs: int, patience: int, seed: int, cfg_extra: dict, retrain: bool = False, log=print):
    """기록구간 내부 창 20, 정상 학습 앞 80% 구간으로 학습·뒤 20%로 조기 종료. 반환 (scores{cal,test,abn}, ref_train_errors, meta, history)."""
    train_fp = hashlib.sha256(np.ascontiguousarray(train[D.SENSORS].to_numpy(float)).tobytes() + seg_train.astype(np.int64).tobytes()).hexdigest()[:16]
    cfg = dict(protocol="common_lstm20", seq=SEQ, epochs=epochs, patience=patience, seed=seed, torch=torch.__version__,
               scaler_mean=[round(float(v), 12) for v in scaler_mean], scaler_scale=[round(float(v), 12) for v in scaler_scale],
               train_fingerprint=train_fp, **cfg_extra)
    key = config_key(cfg)
    hit = None if retrain else _cache_get(cache_dir, key)
    def Z(fr):
        return (fr[D.SENSORS].to_numpy(float) - scaler_mean) / scaler_scale
    def windows(z, seg):
        idx = window_index(seg, SEQ)
        W = np.stack([z[i - SEQ + 1:i + 1] for i in idx]) if len(idx) else np.empty((0, SEQ, 3))
        return idx, W
    ids = np.unique(seg_train)
    cut = ids[int(len(ids) * 0.8)]
    ztr = Z(train)
    idx_a, Wa = windows(ztr[seg_train < cut], seg_train[seg_train < cut])
    idx_b, Wb = windows(ztr[seg_train >= cut], seg_train[seg_train >= cut])
    t0 = time.time()
    if hit is None:
        model, hist = train_ae(Wa, Wb, epochs, patience, seed, log=log)
        out = {}
        for k in ("cal", "test", "abn"):
            idx, W = windows(Z(frames[k]), segs[k])
            s = np.full(len(frames[k]), np.nan)
            s[idx] = last_step_error(model, W)
            out[k] = s
        idx_t, Wt = windows(ztr, seg_train)
        ref = np.full(len(train), np.nan)
        ref[idx_t] = last_step_error(model, Wt)
        ref_holdout = last_step_error(model, Wb)   # 조기 종료용 학습-B 창(적합에 쓰지 않음) → 꼬리 참조용
        _cache_put(cache_dir, key, {**out, "ref": ref, "ref_holdout": ref_holdout, "history": hist.to_records(index=False)})
        meta = dict(cached=False, epochs_run=int(len(hist)), train_seconds=round(time.time() - t0, 1))
    else:
        out = {k: hit[k] for k in ("cal", "test", "abn")}
        ref, ref_holdout, hist = hit["ref"], hit["ref_holdout"], pd.DataFrame(hit["history"])
        meta = dict(cached=True, epochs_run=int(len(hist)), train_seconds=0.0)
    meta.update(cache_key=key, train_windows_fit=int(len(Wa)), train_windows_earlystop=int(len(Wb)), max_epochs=epochs, patience=patience,
                ref_holdout=ref_holdout)
    return out, ref, meta, hist
