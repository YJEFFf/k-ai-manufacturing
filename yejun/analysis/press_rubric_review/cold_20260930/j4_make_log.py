"""J4 위원 검증 기록 모음: 임시 폴더의 실행 로그를 잘라 j4_verification_log.txt 하나로 남긴다(1 MB 미만, 원본·행 단위 예측 없음).
실행: python j4_make_log.py <임시폴더>
"""
import sys
from pathlib import Path

T = Path(sys.argv[1])
parts = []


def add(title, path, keep=None, width=300):
    p = Path(path)
    if not p.exists():
        parts.append(f"== {title}: (없음) {p.name}\n")
        return
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if keep:
        lines = [l for l in lines if keep(l)]
    parts.append(f"== {title} ({p.name})\n" + "\n".join(l[:width] for l in lines) + "\n")


add("한 명령 재현(git 없는 사본, reproduce.py 기본 경로)", T / "j4_quick.log")
add("시험(pytest·node)", T / "j4_tests.log", keep=lambda l: not set(l.strip()) <= set(".s[]% 0123456789"))
add("재실행(E1~E3·지도학습·선정 근거)", T / "j4_reruns.log")
add("모의 운용 simulate.py 출력", T / "j4_field" / "simulate_stdout.txt")
add("콘솔 서버 로그", T / "j4_field" / "serve.log")
add("재보정 보고서(site_report.json)", T / "j4_field" / "site_report.json", width=400)
add("교대 감시 창별 표(monitor_windows.csv)", T / "j4_field" / "monitor_windows.csv", width=400)
add("모의 운용 알림 기록(sim_alerts_B.csv)", T / "j4_field" / "sim_alerts_B.csv", width=400)
out = Path(__file__).with_name("j4_verification_log.txt")
out.write_text("\n".join(parts), encoding="utf-8")
print(out, out.stat().st_size, "bytes")
