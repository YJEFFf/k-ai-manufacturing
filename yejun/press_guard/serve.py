"""로컬 기록 재생·CSV 분석 콘솔. 실제 설비 제어/정지 명령을 보내지 않는다."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import argparse
import io
import json
import time
import threading

import numpy as np
import pandas as pd

from model import GuardModel, StreamDetector, cases, D, HERE, ALPHAS

MAX_UPLOAD=8*1024*1024
MAX_ROWS=50000


def score_threshold(cal,alpha):
    """p=(1+#cal≥s)/(n+1) ≤ α 와 동치인 점수 문턱. 점수가 이 값을 넘으면 경보다. 화면 표시용."""
    n=len(cal); allowed=int(np.floor(alpha*(n+1)-1))
    if allowed<0: return float("inf")
    ordered=np.sort(np.asarray(cal,float))[::-1]
    return float(ordered[allowed]) if allowed<n else float("-inf")


class Console:
    def __init__(self):
        self.normal,self.abnormal,_=D.load()
        self.models={s:GuardModel.load(HERE/"artifacts"/f"guard_{s}.json") for s in D.SPLITS}
        self.cache={}
        self.lock=threading.Lock()

    def analyze(self,request):
        split=str(request.get("split","A")); alpha=float(request.get("alpha",.01))
        if split not in self.models or alpha not in ALPHAS:
            raise ValueError("분할/경보 기준을 확인하세요")
        kind=request.get("dataset","mixed")
        if kind not in ("mixed","normal","abnormal","upload"):
            raise ValueError("알 수 없는 자료 선택")
        key=(split,alpha,kind)
        if kind!="upload" and key in self.cache:
            return self.cache[key]
        if kind=="upload":
            frame=pd.read_csv(io.StringIO(request.get("csv","")))
            truth=None
        else:
            sp=D.split_normal(self.normal,D.segments(self.normal),split)
            frame={"normal":sp["test"],"abnormal":self.abnormal,
                   "mixed":pd.concat([sp["test"],self.abnormal],ignore_index=True)}[kind]
            truth=frame[D.LABEL].astype(int).to_numpy()
        if not 0<len(frame)<=MAX_ROWS:
            raise ValueError(f"1~{MAX_ROWS:,}행의 CSV를 입력하세요")
        start=time.perf_counter()
        stream=StreamDetector(self.models[split],alpha)
        predictions=pd.concat([stream.push(frame.iloc[i:i+128]) for i in range(0,len(frame),128)],ignore_index=True)
        duration=time.perf_counter()-start
        queue=cases(predictions)
        plot=predictions.copy()
        for c in D.SENSORS:
            plot[c]=pd.to_numeric(frame[c],errors="coerce").to_numpy()
        if truth is not None:
            plot["reference_label"]=truth
            if len(queue):
                lookup=plot.groupby("record_id").reference_label.first()
                queue["reference_label"]=queue.record_id.map(lookup)
        result=dict(split=split,alpha=alpha,dataset=kind,source_name="사용자 CSV" if kind=="upload" else "대회 공개 기록 · 평가 구간",
                    stats=dict(rows=len(frame),segments=int(predictions.record_id.nunique()),
                               scored=int(predictions.score.notna().sum()),invalid=int(predictions.status.ne("ok").sum()),
                               alarm_rows=int(predictions.alarm.sum()),notifications=int(predictions.notification.sum()),
                               elapsed_s=duration),
                    calibration_segments=len(self.models[split].cal),threshold=score_threshold(self.models[split].cal,alpha),
                    cases=json.loads(queue.to_json(orient="records")),
                    points=json.loads(plot.to_json(orient="records",double_precision=12)))
        if kind!="upload": self.cache[key]=result
        return result

    def overview(self):
        metrics=pd.read_csv(HERE/"outputs"/"metrics.csv")
        external=HERE.parent/"analysis"/"press_external"/"metrics.csv"
        audit=HERE/"outputs"/"audit.json"; benchmark=HERE/"outputs"/"benchmark.json"
        conditions=HERE/"outputs"/"error_conditions_v2.csv"; robustness=HERE/"outputs"/"robustness_v2.csv"
        cond=pd.read_csv(conditions) if conditions.exists() else pd.DataFrame()
        cond=cond[cond.alpha.eq(.01)&cond.condition.isin(["pos_bin","strongest_component"])] if len(cond) else cond
        rob=pd.read_csv(robustness) if robustness.exists() else pd.DataFrame()
        rob=rob[rob.criterion.eq("conformal")] if len(rob) else rob
        from contracts import execution_errors, read_json
        audit_data=json.loads(audit.read_text()) if audit.exists() else {}
        try:
            errors=execution_errors(read_json(HERE/"outputs"/"manifest.json"),HERE/"outputs",HERE/"artifacts")
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            errors=["실행 기록 오류"]
        if errors:
            audit_data["all_ok"]=False
            audit_data["checks"]=[dict(name="현재 파일과 실행 검증 기록의 연결",ok=False,
                                        detail="파일이 변경되었거나 검증이 미완료입니다. 검증을 다시 실행하세요.")]
        return dict(metrics=json.loads(metrics.to_json(orient="records")),
                    conditions=json.loads(cond.to_json(orient="records")),robustness=json.loads(rob.to_json(orient="records")),
                    external=json.loads(pd.read_csv(external).to_json(orient="records")) if external.exists() else [],
                    audit=audit_data,
                    benchmark=json.loads(benchmark.read_text()) if benchmark.exists() else {})


def handler(console):
    class Handler(BaseHTTPRequestHandler):
        def response(self,payload,status=200,mime="application/json; charset=utf-8"):
            data=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            path=urlparse(self.path).path
            if path=="/api/overview":
                self.response(console.overview()); return
            files={"/":("index.html","text/html"),"/app.js":("app.js","text/javascript"),"/style.css":("style.css","text/css")}
            if path not in files:
                self.response({"error":"찾을 수 없음"},404); return
            name,mime=files[path]
            self.response((HERE/"web"/name).read_bytes(),mime=mime+"; charset=utf-8")

        def do_POST(self):
            if urlparse(self.path).path!="/api/analyze":
                self.response({"error":"찾을 수 없음"},404); return
            try:
                size=int(self.headers.get("Content-Length",0))
                if not 0<size<=MAX_UPLOAD:
                    self.response({"error":"업로드는 8 MB 이하여야 합니다"},413); return
                request=json.loads(self.rfile.read(size))
                if not isinstance(request,dict): raise ValueError("JSON 객체가 필요합니다")
                with console.lock:
                    result=console.analyze(request)
                self.response(result)
            except (ValueError,KeyError,TypeError,pd.errors.ParserError) as error:
                self.response({"error":str(error)},400)

        def log_message(self,fmt,*args):
            print(fmt%args,flush=True)
    return Handler


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port",type=int,default=8765)
    args=ap.parse_args()
    console=Console()
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler(console))
    print(f"Press Guard: http://127.0.0.1:{args.port} (Ctrl+C 종료)",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=="__main__": main()
