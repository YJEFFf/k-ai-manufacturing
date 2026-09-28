"""검토 1(x86-64): 사인 적합 투영 행렬을 컨테이너에서 계산해 npz로 저장한다(macOS 값과 비교는 review1_x86_hats_check.log 참고).

    docker run --rm --platform linux/amd64 -v <x86 사본 루트>:/work -w /work pg-x86 python review1_x86_hats_check.py /work/hats_x86.npz
"""
import sys, platform, numpy as np
sys.path.insert(0, "/work/yejun/press_guard")
import model as M
from press.scores import _hats
out = {}
for w in (6, 8):
    a, b = _hats(w), M.stable_hats(w)
    out[f"default_{w}"] = a; out[f"stable_{w}"] = b
    print(platform.machine(), "win", w, "trace@5Hz default", round(float(np.trace(a[-1])), 6), "stable", round(float(np.trace(b[-1])), 6))
np.savez(sys.argv[1], **out)
