"""UCI 공개 원본 확보·무결성 기록. 원본과 센서 행별 자료는 Git에 넣지 않는다."""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
URL = "https://archive.ics.uci.edu/static/public/447/condition+monitoring+of+hydraulic+systems.zip"
SOURCE = "https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems"


def acquire():
    dest = HERE / "data"
    dest.mkdir(exist_ok=True)
    archive = dest / "hydraulic.zip"
    if not archive.exists():
        partial = dest / "hydraulic.partial"
        with urllib.request.urlopen(URL, timeout=90) as source, partial.open("wb") as sink:
            while block := source.read(1 << 20):
                sink.write(block)
        partial.replace(archive)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failure")
        members = [{"name": i.filename, "bytes": i.file_size, "crc32": f"{i.CRC:08x}"} for i in z.infolist()]
    record = dict(source=SOURCE, download=URL, doi="10.24432/C5CW21", license="CC BY 4.0",
                  citation="Helwig, N., Pignanelli, E., & Schuetze, A. (2015). Condition monitoring of hydraulic systems. UCI Machine Learning Repository.",
                  sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), bytes=archive.stat().st_size,
                  crc_checked=True, members=members,
                  limitations="별도 유압 시험대 60초 사이클. 대회 프레스의 추가 날짜나 독립 실고장 사례가 아니다. VS1 1 Hz, EPS1 전력 100 Hz로 대회 센서와 직접 호환되지 않는다.")
    (HERE / "acquisition.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    return archive


if __name__ == "__main__":
    acquire()
