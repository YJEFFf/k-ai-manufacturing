"""파일럿: 가이드북 LSTM-AE(B0)를 가이드북 코드 그대로(에폭만 축소) 돌려 오분류가 어느 구간에서 나오는지 본다.

가이드북: |x| 변환 → MinMax(앞 15,000행 학습) → 창 20, 라벨 = index+120 → LSTM 64-32-32-64 AE
→ 검증(정상 880 + 이상 300 창)에서 P=R 교차 임계값 → 나머지로 시험. 에폭은 --epochs로 축소(가이드북 800, 조기종료 120).
"""
import argparse, os, sys, time
import numpy as np, pandas as pd
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import tensorflow as tf
from tensorflow.keras import models, layers, optimizers
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from sklearn.preprocessing import MinMaxScaler
from sklearn import metrics
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ap.add_argument('--epochs', type=int, default=60); ap.add_argument('--seed', type=int, default=0)
a = ap.parse_args()
tf.keras.utils.set_random_seed(a.seed)
sub = os.path.join(a.root, 'data', '3_소성가공_예지보전')
normal = pd.read_csv(os.path.join(sub, 'press_data_normal.csv'), index_col=0)
outlier = pd.read_csv(os.path.join(sub, 'outlier_data.csv'), index_col=0)
use_col = ['AI0_Vibration', 'AI1_Vibration', 'AI2_Current']
nd, od = normal.copy(), outlier.copy()
nd[use_col] = nd[use_col].abs(); od[use_col] = od[use_col].abs()
Xn, yn, Xa, ya = nd[use_col], nd['Equipment_state'], od[use_col], od['Equipment_state']
Xtr, ytr, Xten, yten = Xn[:15000], yn[:15000], Xn[15000:], yn[15000:]
sc = MinMaxScaler(); Xtr_s = sc.fit_transform(Xtr); Xten_s = sc.transform(Xten); Xa_s = sc.transform(Xa)
seq = 20
def win(X, y):
    XX, YY, ST = [], [], []
    for i in range(len(X) - seq - 100):
        XX.append(X[i:i + seq]); YY.append(np.asarray(y)[i + seq + 100]); ST.append(i)
    return np.array(XX), np.array(YY), np.array(ST)
X_train, Y_train, _ = win(Xtr_s, ytr)
X_tn, Y_tn, st_tn = win(Xten_s, yten)
X_ta, Y_ta, st_ta = win(Xa_s, ya)
X_vn, Y_vn = X_tn[:880], Y_tn[:880]; X_tn2, Y_tn2, st_tn2 = X_tn[880:], Y_tn[880:], st_tn[880:]
X_va, Y_va = X_ta[:300], Y_ta[:300]; X_ta2, Y_ta2, st_ta2 = X_ta[300:], Y_ta[300:], st_ta[300:]
X_valid = np.vstack((X_vn, X_va)); Y_valid = np.hstack((Y_vn, Y_va))
X_test = np.vstack((X_tn2, X_ta2)); Y_test = np.hstack((Y_tn2, Y_ta2))
X_valid_0 = X_valid[Y_valid == 0]
m = models.Sequential([layers.Input((seq, 3)), layers.LSTM(64, return_sequences=True), layers.LSTM(32, return_sequences=False),
                       layers.RepeatVector(seq), layers.LSTM(32, return_sequences=True), layers.LSTM(64, return_sequences=True),
                       layers.TimeDistributed(layers.Dense(3))])
m.compile(loss='mse', optimizer=optimizers.Adam(0.001))
t0 = time.time()
h = m.fit(X_train, X_train, epochs=a.epochs, batch_size=128, verbose=0,
          callbacks=[ReduceLROnPlateau(monitor='val_loss', factor=0.7, patience=50), EarlyStopping(monitor='val_loss', min_delta=1e-5, patience=120, restore_best_weights=True)],
          validation_data=(X_valid_0, X_valid_0))
fit_s = time.time() - t0
def last(X): return X[:, -1, :]
mse_v = np.mean((last(X_valid) - last(m.predict(X_valid, verbose=0))) ** 2, axis=1)
p, r, th = metrics.precision_recall_curve(Y_valid, mse_v)
idx = [i for i, (pp, rr) in enumerate(zip(p, r)) if pp == rr]
k = idx[0] if idx else int(np.argmin(np.abs(p[:-1] - r[:-1])))
thr = th[k]
mse_t = np.mean((last(X_test) - last(m.predict(X_test, verbose=0))) ** 2, axis=1)
pred = (mse_t > thr).astype(int)
cm = metrics.confusion_matrix(Y_test, pred)
print(f'epochs_run={len(h.history["loss"])} fit_s={fit_s:.0f} thr={thr:.5f} P=R@valid≈{p[k]:.3f}')
print('confusion [[TN FP][FN TP]]:', cm.tolist(), 'acc=%.4f F1=%.4f' % (metrics.accuracy_score(Y_test, pred), metrics.f1_score(Y_test, pred)))
# 오분류 위치: 시험 정상 창의 시작 행(원본 기준 15000+st) → 시각 구간별 FP 비율
t = pd.to_datetime(normal.TimeStamp.values)
start_rows = 15000 + st_tn2
mins = (t[start_rows] - t[0]).total_seconds() / 60
fp = pred[:len(Y_tn2)] == 1
bins = [57, 60, 72, 78]
for lo, hi in zip(bins[:-1], bins[1:]):
    msk = (mins >= lo) & (mins < hi)
    print(f'normal test windows {lo}-{hi} min: n={msk.sum()} FP={fp[msk].sum()} ({fp[msk].mean():.3f})')
