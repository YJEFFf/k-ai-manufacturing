"""로컬 Chrome/CDP로 실제 탭·선택·재생·업로드·내보내기 확인. 웹 서버가 실행 중이어야 한다."""
from pathlib import Path
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
import sys
import websocket

HERE=Path(__file__).resolve().parent
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8767"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main():
    with tempfile.TemporaryDirectory(prefix="guard-browser-") as tmp:
        root=Path(tmp)
        proc=subprocess.Popen([CHROME,"--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check",
            "--remote-allow-origins=*","--remote-debugging-port=0",f"--user-data-dir={root}","about:blank"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ws=None
        try:
            deadline=time.monotonic()+20
            while not (root/"DevToolsActivePort").exists():
                if time.monotonic()>deadline: raise TimeoutError("Chrome 시작 실패")
                time.sleep(.1)
            port=(root/"DevToolsActivePort").read_text().splitlines()[0]
            pages=json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
            ws=websocket.create_connection(next(p["webSocketDebuggerUrl"] for p in pages if p["type"]=="page"),timeout=20)
            sequence=0; errors=[]
            def call(method,params=None):
                nonlocal sequence
                sequence+=1; current=sequence
                ws.send(json.dumps(dict(id=current,method=method,params=params or {})))
                while True:
                    message=json.loads(ws.recv())
                    if message.get("method")=="Runtime.exceptionThrown": errors.append(message["params"])
                    if message.get("id")==current:
                        if "error" in message: raise RuntimeError(message["error"])
                        return message.get("result",{})
            def js(expression):
                result=call("Runtime.evaluate",dict(expression=expression,returnByValue=True,awaitPromise=True))
                if "exceptionDetails" in result: raise RuntimeError(result["exceptionDetails"])
                return result.get("result",{}).get("value")
            def until(expression):
                deadline=time.monotonic()+30
                while not js(expression):
                    if time.monotonic()>deadline: raise TimeoutError(expression)
                    time.sleep(.1)
            call("Runtime.enable"); call("Page.enable")
            call("Emulation.setDeviceMetricsOverride",dict(width=1440,height=1100,deviceScaleFactor=1,mobile=False))
            call("Page.navigate",dict(url=URL))
            until("document.getElementById('k-case')?.textContent==='21'")
            assert js("['k-case','k-alarm','k-coverage','k-segment'].map(id=>document.getElementById(id).textContent)")==['21','556','100.0%','141']
            assert js("document.querySelectorAll('.queue-item').length")==21
            shot=call("Page.captureScreenshot",dict(format="png"))
            (HERE/"codex_console.png").write_bytes(base64.b64decode(shot["data"]))
            js("document.querySelector('[data-tab=evidence]').click()")
            assert js("document.querySelectorAll('#conditions tbody tr').length")==8
            assert js("document.querySelectorAll('#robustness tbody tr').length")==12
            js("document.querySelector('[data-tab=external]').click()")
            assert js("document.querySelectorAll('#external-table tbody tr').length")==6
            js("document.querySelector('[data-tab=monitor]').click();document.querySelectorAll('.queue-item')[1].click();document.getElementById('scrubber').value=0;document.getElementById('scrubber').dispatchEvent(new Event('input'))")
            rect=js("(()=>{const r=document.querySelector('#score-chart svg').getBoundingClientRect();return {x:r.x+60,y:r.y+40};})()")
            call("Input.dispatchMouseEvent",dict(type="mouseMoved",**rect))
            js("document.getElementById('replay').click()")
            time.sleep(.3)
            assert js("Number(document.getElementById('scrubber').value)")>0
            js("if(document.getElementById('replay').textContent.includes('중지'))document.getElementById('replay').click();document.getElementById('split').value='B';document.getElementById('alpha').value='0.03';document.getElementById('alpha').dispatchEvent(new Event('change'))")
            until("!document.getElementById('analyze').disabled && document.getElementById('k-case').textContent==='26'")
            assert js("document.getElementById('k-alarm').textContent")=="576"
            js("document.getElementById('filter').value='waveform';document.getElementById('filter').dispatchEvent(new Event('change'))")
            filtered=js("document.querySelectorAll('.queue-item').length")
            assert 0<filtered<26
            call("Browser.setDownloadBehavior",dict(behavior="allow",downloadPath=str(root)))
            js("window.originalURL=URL.createObjectURL;URL.createObjectURL=b=>{window.exportBlob=b;return originalURL(b);};document.getElementById('export').click()")
            exported=js("exportBlob.text()")
            assert len(exported.splitlines())==filtered+1 and "record_id" in exported.splitlines()[0]
            sys.path.insert(0,str(HERE.parents[1]/"press_guard"))
            from model import D
            _,abnormal,_=D.load()
            upload=abnormal.iloc[:12].copy();upload.loc[2,D.SENSORS[0]]=float('nan')
            csv=root/"upload.csv";upload.to_csv(csv,index=False)
            js("document.getElementById('filter').value='all';document.getElementById('filter').dispatchEvent(new Event('change'))")
            doc=call("DOM.getDocument")
            node=call("DOM.querySelector",dict(nodeId=doc["root"]["nodeId"],selector="#file"))
            call("DOM.setFileInputFiles",dict(nodeId=node["nodeId"],files=[str(csv)]))
            until("document.getElementById('message').textContent.includes('upload.csv · 12행')")
            assert "수집 오류 1행" in js("document.getElementById('k-quality').textContent")
            assert "참조 라벨 없음"==js("document.getElementById('reference').textContent")
            assert not errors,errors
            result=dict(default_kpis=[21,556,"100.0%",141],condition_rows=8,robustness_rows=12,external_rows=6,
                        B_alpha03_notifications=26,B_alpha03_alarm_rows=576,export_rows=filtered,
                        upload_rows=12,upload_invalid_rows=1,empty_replay_hover=True,replay=True,console_exceptions=errors)
            (HERE/"codex_browser_results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False))
        finally:
            if ws: ws.close()
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()


if __name__=="__main__":main()
