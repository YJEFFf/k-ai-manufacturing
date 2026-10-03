"""Inference on an unlabeled CSV using an explicitly frozen completed-record model."""
import argparse
import pickle
from pathlib import Path
from dataclasses import replace

from common import core, pd, np, csv, save, sha


def predict(input_path, artifact, output):
    raw = pd.read_csv(input_path)
    try:
        records, audit = core.records_from_frame(raw[["TimeStamp"]+core.COLS])
    except (ValueError, KeyError, TypeError) as error:
        save(Path(output).with_suffix(".input_error.json"), dict(status="input_contract_failed",
             input_sha256=sha(input_path), input_rows=len(raw), excluded_from_success=True, error=str(error)))
        raise
    state = pickle.loads(Path(artifact).read_bytes())  # Only this project's trusted local artifact.
    records = [replace(r, source_namespace="inference") for r in records]
    f = core.features(records)
    rows = []
    origin = pd.Timestamp(raw.TimeStamp.iloc[0])
    for name, model in state["models"].items():
        prediction = model.predict(f)
        for i, record in enumerate(records):
            for source_row in record.source_rows:
                rows.append(dict(model=name, source_row=source_row, record=record.parent,
                    input_timestamp=raw.TimeStamp.iloc[source_row],
                    decision_available_timestamp=str(origin+pd.Timedelta(minutes=record.decision_m)),
                    score=prediction["score"][i], p_normal_tail=prediction["p"][i],
                    reference=prediction["route"][i], n_cal=prediction["n_cal"][i], alpha=.05,
                    supported=prediction["supported"][i], mechanical_request=prediction["bit"][i],
                    quality_request=prediction["quality"][i],
                    mapping_scope="completed-record retrospective mapping; not causal row prediction"))
    csv(output, rows)
    save(Path(output).with_suffix(".manifest.json"), dict(input_sha256=sha(input_path),
         artifact_sha256=sha(artifact), data_contract=audit, output_rows=len(rows),
         labels_used=False, model_ids=list(state["models"])))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--artifact", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    predict(args.input, args.artifact, args.output)
