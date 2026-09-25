"""CSV를 고정 모델로 순차 추론한다. --chunk가 달라도 결과는 같아야 한다."""
from pathlib import Path
import argparse
import pandas as pd
from model import GuardModel, StreamDetector, cases, HERE


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model",type=Path,default=HERE/"artifacts"/"guard_A.json")
    ap.add_argument("--input",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--cases",type=Path)
    ap.add_argument("--alpha",type=float,choices=[.01,.03,.05],default=.01)
    ap.add_argument("--chunk",type=int,default=128)
    args=ap.parse_args()
    if args.chunk<1: ap.error("chunk는 양수여야 한다")
    stream=StreamDetector(GuardModel.load(args.model),args.alpha)
    parts=[stream.push(part) for part in pd.read_csv(args.input,chunksize=args.chunk)]
    result=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(args.out,index=False)
    queue=cases(result) if len(result) else pd.DataFrame()
    if args.cases:
        args.cases.parent.mkdir(parents=True,exist_ok=True)
        queue.to_csv(args.cases,index=False)
    print(f"{len(result)}행 처리, 점검 대기 {len(queue)}구간 → {args.out}")


if __name__=="__main__": main()
