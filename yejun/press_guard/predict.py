"""저장 모델로 순차 추론한다(학습 없음). --chunk가 달라도 결과는 같다.

    python predict.py --input 기록.csv --out 예측.csv [--model artifacts/guard_A.json] [--cases 대기열.csv] [--alpha 0.01] [--prior 0.01]
    python predict.py --split A --out test_predictions_A.csv     # 제출용 테스트 예측 파일을 저장 모델로 다시 만든다

--split: 분할의 정상 평가 기록과 이상 기록을 저장 모델(artifacts/guard_<split>.json, probability_<split>.json)로 추론해
train.py가 쓴 outputs/test_predictions_<split>.csv와 같은 파일을 만든다. 이상 행의 확률 열은 평가용 교차 적합 값이다
(그 이상 기록을 뺀 보정기, 이상 라벨 사용). 끝에 SHA-256과 학습 실행 manifest의 기록을 대조해 보인다.
"""
from pathlib import Path
import argparse
import json
import sys

import pandas as pd

from model import StreamDetector, cases, incidents, timing_warning, D, HERE, load_bundle
import runtime


def stream(model, frame, alpha, prior, chunk):
    detector = StreamDetector(model, alpha, prior)
    parts = [detector.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def split_file(split, chunk=128):
    """train.py의 test_predictions_<split>.csv를 저장 모델로 다시 만든다(α=1%, 사전 비율 1%)."""
    from train import oof_likelihood_ratio, use_oof, test_prediction_file
    normal, abnormal, _ = D.load()
    sp = D.split_normal(normal, D.segments(normal), split)
    model = load_bundle(HERE / "artifacts" / f"guard_{split}.json")
    pn, pa = stream(model, sp["test"], .01, None, chunk), stream(model, abnormal, .01, None, chunk)
    pa = use_oof(pa, oof_likelihood_ratio(model, sp["cal"], abnormal))
    pn["probability_source"], pa["probability_source"] = "deployment_calibrator", "leave_one_record_out"
    return test_prediction_file(pn, pa)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=HERE / "artifacts" / "guard_A.json")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--split", choices=tuple(D.SPLITS), help="제출용 테스트 예측 파일 재생성")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cases", type=Path)
    ap.add_argument("--alpha", type=float, choices=[.01, .03, .05], default=.01)
    ap.add_argument("--chunk", type=int, default=128)
    ap.add_argument("--prior", type=float, default=None, help="이상 행 비율 π 가정(기본 1%%). 기록 확률은 같은 π를 쓰는 근사이며 경보에는 영향 없음")
    args = ap.parse_args(argv)
    runtime.setup()
    if args.chunk < 1:
        ap.error("chunk는 양수여야 한다")
    if (args.input is None) == (args.split is None):
        ap.error("--input과 --split 중 하나만 준다")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.split:
        result = split_file(args.split, args.chunk)
        result.to_csv(args.out, index=False)
        digest = D.sha256_file(args.out)
        name = f"test_predictions_{args.split}.csv"
        manifest = HERE / "outputs" / "manifest.json"
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("outputs", {}).get(name) if manifest.exists() else None
        verdict = "학습 실행 기록 없음" if recorded is None else ("학습 실행과 같음" if recorded == digest else "학습 실행과 다름")
        print(f"{len(result)}행 → {args.out} · SHA-256 {digest[:16]}… · {verdict}")
        return 0 if recorded in (None, digest) else 1
    model = load_bundle(args.model)
    if model.probability is None:
        print("안내: 라벨 확률 보정기가 없어 확률·우도비 열 4개는 비어 있고 --prior(π)는 쓰이지 않습니다.", file=sys.stderr)
    result = stream(model, pd.read_csv(args.input), args.alpha, args.prior, args.chunk)
    result.to_csv(args.out, index=False)
    queue = cases(result) if len(result) else pd.DataFrame()
    if args.cases:
        args.cases.parent.mkdir(parents=True, exist_ok=True)
        queue.to_csv(args.cases, index=False)
    warn = timing_warning(result) if len(result) else ""
    if warn:
        print("경고: " + warn)
    print(f"{len(result)}행 처리, 사건 {len(incidents(queue)) if len(queue) else 0}개(건 {len(queue)}) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
