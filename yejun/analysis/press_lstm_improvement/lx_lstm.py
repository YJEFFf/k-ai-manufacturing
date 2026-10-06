"""LSTM 오토인코더 변형 학습·채점.

예준 yejun/press_submission/press/lstm_ae.py의 가이드북 구조(LSTM 64→32 인코더, 마지막 은닉 상태 반복, 32→64 디코더)와
학습 루프(Adam 1e-3, 배치 128, ReduceLROnPlateau 0.7/50, 조기 종료, 최적 가중치 복원)를 그대로 옮기고 아래만 바꿀 수 있게 했다.
- 창 길이 W
- 기록 앞부분 처리 warm
  · none: 창이 다 찬 행만 점수(가이드북·lstm20)
  · edge: 모든 행에 점수, 모자라는 앞쪽은 기록 첫 행을 반복해 채운 창
  · var : 모든 행에 점수, 채우지 않고 실제 길이(min(위치+1, W))의 창을 그대로 넣는다(길이별 배치, 손실·요약에 패딩 없음)
- 용량 (h1, h2): 기본 (64, 32)
- 학습 예산 (최대 에폭, 조기 종료 인내)
- 학습 자료 data: early80(기본, 공통 프로토콜) = 학습 기록 앞 80% 적합·뒤 20% 조기 종료,
  late80 = 앞 20%로 조기 종료·뒤 80%(valid에 가까운 쪽)로 적합
기본값(W 20, none, 64-32, 300/30, early80)은 예준 protocol_common(lstm20)과 같은 창·초기화·학습 순서다.
같은 점수가 나오는지는 02_valid_select.py가 결과를 열기 전에 단언으로 확인한다.
점수 재료로 창마다 시점·채널별 제곱 오차를 만들고 아래 FEATS 요약만 저장한다(채점 방식은 lx_scoring.py).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

FEATS = ["raw_last", "last_c0", "last_c1", "last_c2", "mean_c0", "mean_c1", "mean_c2",
         "max_c0", "max_c1", "max_c2", "max_t_meanc"]


class LSTMAEx(nn.Module):
    """예준 LSTMAE와 같은 층·생성 순서. (h1, h2) = (64, 32)이면 같은 초기화가 나온다. 입력 길이는 창마다 달라도 된다."""

    def __init__(self, n_features: int = 3, h1: int = 64, h2: int = 32):
        super().__init__()
        self.e1 = nn.LSTM(n_features, h1, batch_first=True)
        self.e2 = nn.LSTM(h1, h2, batch_first=True)
        self.d1 = nn.LSTM(h2, h2, batch_first=True)
        self.d2 = nn.LSTM(h2, h1, batch_first=True)
        self.out = nn.Linear(h1, n_features)

    def forward(self, x):
        h, _ = self.e1(x)
        h, _ = self.e2(h)
        z = h[:, -1:, :].repeat(1, x.shape[1], 1)
        h, _ = self.d1(z)
        h, _ = self.d2(h)
        return self.out(h)


def _setup(seed, h1, h2, lr, lr_factor, lr_patience):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    model = LSTMAEx(3, h1, h2)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=lr_factor, patience=lr_patience)
    return gen, model, opt, sched


def train_ae(Xtr, Xval, epochs, patience, seed=0, h1=64, h2=32, lr=1e-3, batch=128, lr_factor=0.7, lr_patience=50, min_delta=1e-5):
    """예준 lstm_ae.train_ae와 같은 순서의 학습 루프(모델 생성만 LSTMAEx로). 창 길이가 모두 같을 때(none·edge)."""
    gen, model, opt, sched = _setup(seed, h1, h2, lr, lr_factor, lr_patience)
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
            loss = loss_fn(model(xb), xb)
            loss.backward()
            opt.step()
            tot += float(loss) * len(xb)
        model.eval()
        with torch.no_grad():
            vl = float(loss_fn(model(Xv), Xv))
        sched.step(vl)
        hist.append((ep + 1, tot / len(Xt), vl))
        if vl < best - min_delta:
            best, wait, best_state = vl, 0, {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, np.array(hist)


def train_ae_var(fit: dict, hold: dict, epochs, patience, seed=0, h1=64, h2=32, lr=1e-3, batch=128, lr_factor=0.7,
                 lr_patience=50, min_delta=1e-5):
    """길이가 다른 창(var)용 학습 루프. 배치는 같은 길이끼리 묶고 배치 순서를 섞는다. 조기 종료 손실은 원소 가중 평균."""
    gen, model, opt, sched = _setup(seed, h1, h2, lr, lr_factor, lr_patience)
    loss_fn = nn.MSELoss()
    Xt = {L: torch.tensor(W, dtype=torch.float32) for L, (_, W) in fit.items() if len(W)}
    Xv = {L: torch.tensor(W, dtype=torch.float32) for L, (_, W) in hold.items() if len(W)}
    n_v = sum(x.numel() for x in Xv.values())
    best, best_state, wait, hist = np.inf, None, 0, []
    for ep in range(epochs):
        model.train()
        batches = []
        for L in sorted(Xt):
            perm = torch.randperm(len(Xt[L]), generator=gen)
            batches += [(L, perm[i:i + batch]) for i in range(0, len(perm), batch)]
        tot, n_el = 0.0, 0
        for j in torch.randperm(len(batches), generator=gen).tolist():
            L, ix = batches[j]
            xb = Xt[L][ix]
            opt.zero_grad()
            loss = loss_fn(model(xb), xb)
            loss.backward()
            opt.step()
            tot += float(loss) * xb.numel()
            n_el += xb.numel()
        model.eval()
        with torch.no_grad():
            vl = sum(float(((model(x) - x) ** 2).sum()) for x in Xv.values()) / n_v
        sched.step(vl)
        hist.append((ep + 1, tot / n_el, vl))
        if vl < best - min_delta:
            best, wait, best_state = vl, 0, {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, np.array(hist)


def record_starts(seg: np.ndarray) -> np.ndarray:
    """각 행이 속한 기록의 첫 행 번호."""
    seg = np.asarray(seg)
    new = np.r_[True, seg[1:] != seg[:-1]]
    return np.maximum.accumulate(np.where(new, np.arange(len(seg)), 0))


def windows(z: np.ndarray, seg: np.ndarray, W: int, warm: str):
    """(점수를 받을 행 번호, 창 (n, W, 3)). none은 예준 window_index와 같은 행·같은 순서. var는 prefix_groups를 쓴다."""
    if warm == "none":
        idx = np.arange(W - 1, len(seg))
        idx = idx[seg[idx] == seg[idx - W + 1]]
        Wn = np.stack([z[i - W + 1:i + 1] for i in idx]) if len(idx) else np.empty((0, W, z.shape[1]))
        return idx, Wn
    if warm != "edge":
        raise ValueError(warm)
    start = record_starts(seg)
    idx = np.arange(len(seg))
    src = np.maximum(idx[:, None] - (W - 1) + np.arange(W)[None, :], start[:, None])
    return idx, z[src]


def prefix_groups(z: np.ndarray, seg: np.ndarray, W: int) -> dict:
    """var: 행마다 실제 길이 L = min(기록 안 위치 + 1, W)의 창. 반환 {L: (행 번호, 창 (n_L, L, 3))}."""
    pos = np.arange(len(seg)) - record_starts(seg)
    Ls = np.minimum(pos + 1, W)
    out = {}
    for L in range(1, W + 1):
        idx = np.flatnonzero(Ls == L)
        out[L] = (idx, z[idx[:, None] - (L - 1) + np.arange(L)[None, :]] if len(idx) else np.empty((0, L, z.shape[1])))
    return out


def error_features(model, Wn: np.ndarray, batch: int = 2048) -> np.ndarray:
    """창마다 FEATS 순서의 오차 요약. raw_last는 예준 last_step_error와 같은 float32 계산."""
    if len(Wn) == 0:
        return np.empty((0, len(FEATS)))
    out = []
    with torch.no_grad():
        for i in range(0, len(Wn), batch):
            xb = torch.tensor(Wn[i:i + batch], dtype=torch.float32)
            xh = model(xb)
            raw_last = ((xb[:, -1, :] - xh[:, -1, :]) ** 2).mean(1)
            E = (xb - xh) ** 2
            f = torch.cat([raw_last[:, None], E[:, -1, :], E.mean(1), E.max(1).values, E.mean(2).max(1).values[:, None]], 1)
            out.append(f.numpy().astype(np.float64))
    return np.concatenate(out)


def frame_features(model, z: np.ndarray, seg: np.ndarray, W: int, warm: str) -> np.ndarray:
    """임의 구간(valid·test·주입 기록 등)의 행별 오차 요약. 창이 없는 행은 NaN."""
    seg = np.asarray(seg)
    F = np.full((len(z), len(FEATS)), np.nan)
    if warm == "var":
        for L, (idx, Wn) in prefix_groups(z, seg, W).items():
            if len(idx):
                F[idx] = error_features(model, Wn)
        return F
    idx, Wn = windows(z, seg, W, warm)
    if len(idx):
        F[idx] = error_features(model, Wn)
    return F


def split_train(seg_tr: np.ndarray, data: str):
    """학습 기록을 적합·조기 종료로 나눈다. early80 = 예준 공통 프로토콜(앞 80% 적합)."""
    ids = np.unique(seg_tr)
    if data == "late80":
        cut = ids[int(len(ids) * 0.2)]
        return seg_tr >= cut, seg_tr < cut
    if data != "early80":
        raise ValueError(data)
    cut = ids[int(len(ids) * 0.8)]
    return seg_tr < cut, seg_tr >= cut


def run(job: dict) -> dict:
    """작업 하나(분할·설정·시드)를 학습하고 프레임별 오차 요약을 cache/runs/에 저장한다. 이미 있으면 건너뛴다."""
    path = Path(job["path"])
    if path.exists() and not job.get("check_only"):
        return dict(job, skipped=True)
    inp = np.load(job["inputs"], allow_pickle=False)
    W, warm, seed = job["W"], job["warm"], job["seed"]
    z_tr, seg_tr = inp["z_train"], inp["seg_train"]
    fit, hold = split_train(seg_tr, job.get("data", "early80"))
    t0 = time.time()
    if warm == "var":
        model, hist = train_ae_var(prefix_groups(z_tr[fit], seg_tr[fit], W), prefix_groups(z_tr[hold], seg_tr[hold], W),
                                   job["epochs"], job["patience"], seed, job["h1"], job["h2"])
        n_fit, n_hold = int(fit.sum()), int(hold.sum())
    else:
        _, Wa = windows(z_tr[fit], seg_tr[fit], W, warm)
        _, Wb = windows(z_tr[hold], seg_tr[hold], W, warm)
        model, hist = train_ae(Wa, Wb, job["epochs"], job["patience"], seed, job["h1"], job["h2"])
        n_fit, n_hold = int(len(Wa)), int(len(Wb))
    arrays = {}
    for k in ("valid_normal", "test_normal", "abnormal"):
        z, seg = inp[f"z_{k}"], inp[f"seg_{k}"]
        arrays[f"F_{k}"] = frame_features(model, z, seg, W, warm)
        arrays[f"pos_{k}"] = np.arange(len(seg)) - record_starts(seg)
    Fh = frame_features(model, z_tr[hold], seg_tr[hold], W, warm)   # 정규화 참조: 조기 종료 구간(적합에 안 씀)
    ok = np.isfinite(Fh[:, 0])
    arrays["F_hold"] = Fh[ok]
    arrays["pos_hold"] = (np.arange(int(hold.sum())) - record_starts(seg_tr[hold]))[ok]
    arrays["hist"] = hist
    meta = dict(job, epochs_run=int(len(hist)), best_val=float(hist[:, 2].min()), train_seconds=round(time.time() - t0, 1),
                n_fit_windows=n_fit, n_hold_windows=n_hold)
    if job.get("model_path"):   # 강건성 시험(주입한 구간을 다시 채점)에 쓸 가중치
        Path(job["model_path"]).parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), job["model_path"])
    if job.get("check_only"):   # 결정성 확인용 재학습: 캐시를 덮어쓰지 않고 오차 요약만 돌려준다
        return dict(meta, arrays=arrays)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez(tmp, meta=json.dumps(meta), **arrays)
    tmp.replace(path)
    return meta


def load_model(path, h1: int, h2: int) -> LSTMAEx:
    torch.set_num_threads(1)
    model = LSTMAEx(3, h1, h2)
    model.load_state_dict(torch.load(path, weights_only=True))
    model.eval()
    return model
