import os, re, io, json, zipfile, unicodedata, time
from collections import Counter, defaultdict
ROOT = "데이터셋"
NFC = lambda s: unicodedata.normalize("NFC", s)
# KAMP DATASET_SEQ -> (name, task tag, relevance) from yejun/KAMP_가이드북_관련데이터셋_조사.md
KAMP = {
 1:("제조 현장용 OCR학습","기타","무관"), 2:("Ford 엔진 진동","③","시계열 분류 참고(다른 설비)"), 3:("CNC 머신","기타","무관"),
 4:("사출성형기","① 원자료","① 대회 CSV 4개의 원본(시각·부품·원값 포함)"), 5:("용접기","② 원자료","② 대회 원본"),
 6:("머신비전","①/④","사출품 열화상 검사 참고"), 7:("프레스기","③","프레스 품질·공정 최적화(펌프 고장 아님)"),
 8:("용해탱크","기타","무관"), 9:("교반구동장치","③","다른 모터 설비 진동 감시"), 10:("살균기","기타","무관"),
 11:("건조구동장치","③","구동부 Z축 진동 이탈 분석"), 12:("X-ray 검사장비","④ 원자료","④ 대회 원본"),
 16:("제조현장용 Scene-Text Recognition 학습","기타","무관"), 18:("회전기계 고장유형","③","Rotor testbed 진동 4채널 고장분류"),
 19:("공정운영 최적화","기타","무관"), 20:("품질 이상탐지,진단(전해탈지)","기타","무관"), 21:("품질 이상탐지,진단(도금욕)","기타","무관"),
 23:("장비이상 조기탐지","③","열풍건조 PLC + 팬 소리 WAV"), 25:("품질 이상탐지,진단(크로메이트)","④","표면처리 영상 검사 참고"),
 26:("공급망 최적화","⑤","발주 수요 예측 참고"), 27:("자원 최적화","⑤ 원자료","⑤ 대회 원본"), 28:("생산공정 최적화","①","공정조건 추천 방법론"),
 29:("제조현장 안전관리","④","YOLO 박스 라벨 형식 참고"), 30:("생산계획 최적화","⑤","스케줄 제약 모델링"), 36:("표면처리 공급망 최적화","⑤","생산계획 제약 참고"),
 37:("열처리 공급망 최적화","⑤","수요 예측 참고"), 40:("사출성형 공급망 최적화","①/⑤","수주·생산계획 시계열"), 41:("표면처리 자원 최적화","⑤","Power_Usage 열 보유"),
 42:("화장품 품질보증","기타","무관"), 43:("열처리 예지보전","③","다변량 설비 상태 감시"), 44:("정밀가공 자원최적화","기타","무관"),
 45:("로봇용접 예지보전","②/③","로봇 진동·전류 이상탐지"), 46:("소성가공 자원최적화","⑤","프레스 4대·로봇 2대 전류·전력"), 47:("전자부품(음향기기) 품질보증","기타","무관"),
 48:("소성가공 예지보전","③ 원자료","③ 대회 원본"), 49:("소성가공 품질보증","①","압출 품질 예측"), 50:("정밀가공 품질보증","기타","무관"),
 51:("용접 예지보전","②","노즐 이상 정상/이상 시계열"), 52:("용접 공정최적화","②","파이프 용접 품질분류 74만 행"), 53:("주조 공정최적화","①","불량 분류·변수 범위"),
 54:("주조 설비 예지보전","①","예열/정상 상태 구분"), 55:("주조 품질보증","①","Shot별 양/불량 이력"), 56:("사출성형 예지보전","①","Shot 단위 설비 상태 라벨"),
 57:("전자부품(배터리팩) 예지보전","②","레이저 용접 설비 시계열"), 58:("전자부품(배터리팩) 품질보증","기타","무관"), 59:("기계부품 품질보증","③","냉간단조 설비 전류·경보"),
 60:("열처리 품질보증","기타","무관"), 61:("열처리 공정최적화","기타","무관"), 62:("의류 품질보증","기타","무관"), 90:("의류 공정최적화","기타","무관"),
}
ENG = {"OCR":1,"FordEngine":2,"CNC":3,"Molding":4,"Machinevision":6,"Press":7,"Meltingtank":8,"Mixer":9,"Pasteurizer":10,"Drier":11,"Dryer":11}
norm = lambda s: re.sub(r"[\s,_\-]", "", NFC(s))
def ident(name):
    n = NFC(name)
    if n == "Investment_Casting.csv": return 53
    m = re.match(r"^\d+\. (Dataset|Guidebook)_(\w+)\.", n)
    if m: return ENG.get(m.group(2))
    if n.startswith("2. 용접기"): return 5
    if n.startswith("프레스_유압펌프"): return 48
    if n.startswith("미확인"): return None
    core = re.sub(r"^(Dataset_|Dataset |Guidebook_)", "", n); core = re.sub(r" AI 데이터셋.*$", "", core)
    best = None
    for k, (nm, _, _) in KAMP.items():
        if norm(nm) == norm(core): return k
        if norm(nm) in norm(core) or norm(core) in norm(nm): best = best or k
    return best
TEXT = {".csv",".tsv",".txt",".json",".xml"}
def count_rows(zf, info, cap=600_000_000):
    if info.file_size > cap: return None
    n = 0
    with zf.open(info) as f:
        while True:
            b = f.read(8 << 20)
            if not b: break
            n += b.count(b"\n")
    return max(n - 1, 0)
def scan_zip(path):
    try: zf = zipfile.ZipFile(path)
    except Exception as e: return {"readable": False, "error": type(e).__name__}
    infos = [i for i in zf.infolist() if not i.is_dir()]
    ext = Counter(os.path.splitext(i.filename)[1].lower() for i in infos)
    csv_rows, big = {}, 0
    for i in infos:
        e = os.path.splitext(i.filename)[1].lower()
        if e == ".csv":
            r = count_rows(zf, i)
            if r is None: big += 1
            else: csv_rows[NFC(os.path.basename(i.filename))] = r
    return {"readable": True, "n_files": len(infos), "uncompressed": sum(i.file_size for i in infos),
            "ext": dict(ext.most_common(6)), "csv_rows": csv_rows, "csv_uncounted": big}
rows = []
t0 = time.time()
for dirpath, dirs, files in os.walk(ROOT):
    for f in files:
        if f.startswith("."): continue
        p = os.path.join(dirpath, f); rel = NFC(os.path.relpath(p, ROOT)); size = os.path.getsize(p)
        kind = "guidebook" if f.lower().endswith(".pdf") else ("csv" if f.lower().endswith(".csv") else ("xlsx" if f.lower().endswith(".xlsx") else "archive"))
        rec = {"path": rel, "bytes": size, "kind": kind, "id": ident(f if dirpath == ROOT else NFC(os.path.relpath(dirpath, ROOT)).split("/")[0])}
        if kind == "archive":
            rec.update(scan_zip(p) if size > 0 else {"readable": False, "error": "0 bytes"})
        elif kind == "csv":
            with open(p, "rb") as fh: rec["rows"] = sum(b.count(b"\n") for b in iter(lambda: fh.read(8 << 20), b"")) - 1
        rows.append(rec)
json.dump(rows, open(os.environ["OUT"], "w"), ensure_ascii=False, indent=1)
print(f"scanned {len(rows)} files in {time.time()-t0:.0f}s")
