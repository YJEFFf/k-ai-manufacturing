"""Audit ESPset IDs/labels and reserve whole pumps, without inspecting features."""
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parents[1]


def main():
    counts = Counter()
    units = Counter()
    unit_labels = defaultdict(set)
    sample_ids = set()
    duplicates = 0
    with zipfile.ZipFile(HERE / "data/espset/features.zip") as archive:
        with archive.open("features.csv") as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter=";")
            columns = reader.fieldnames
            if not {"id", "esp_id", "label"}.issubset(columns):
                raise ValueError("ESPset schema changed")
            for row in reader:
                unit, label = row["esp_id"], row["label"]
                counts[label] += 1
                units[unit] += 1
                unit_labels[unit].add(label)
                key = (unit, row["id"])
                duplicates += key in sample_ids
                sample_ids.add(key)
    if set(counts) != {"Normal", "Unbalance", "Faulty sensor", "Rubbing", "Misalignment"}:
        raise ValueError("Unexpected label vocabulary")
    audit = dict(rows=sum(counts.values()), columns=columns, unique_esp_ids=len(units),
                 label_counts=dict(counts.most_common()), rows_per_esp_min=min(units.values()),
                 rows_per_esp_max=max(units.values()),
                 units_with_multiple_labels=sum(len(labels) > 1 for labels in unit_labels.values()),
                 duplicate_unit_sample_ids=duplicates,
                 scope="metadata/ID/label counts only; no feature statistics or model outcomes; not a time-domain dataset")
    ids = sorted(units, key=lambda unit: hashlib.sha256(f"press-master-v1|{unit}".encode()).hexdigest())
    if len(ids) != 11:
        raise ValueError("Pinned dataset should contain 11 pump IDs")
    roles = ["fit"] * 5 + ["dev"] * 2 + ["cal"] * 2 + ["test"] * 2
    reservation = dict(doi="10.17632/m268jsw339.3",
                       assignment="Sort SHA256(UTF8(press-master-v1|str(esp_id))); first 5 fit, next 2 dev, next 2 cal, last 2 test; all spectra/features of an esp_id stay together.",
                       files=[dict(esp_id=unit, split=role) for unit, role in zip(ids, roles)],
                       scope="IDs and labels seen for structural counts. No feature statistics/model outcomes. Do not interpret as unseen raw data or temporal test.")
    prior_path = HERE / "evidence/espset_group_reservation.json"
    if prior_path.exists() and json.loads(prior_path.read_text())["files"] != reservation["files"]:
        raise ValueError("Reservation changed; inspect source version before overwriting")
    for name, obj in [("espset_audit.json", audit), ("espset_group_reservation.json", reservation)]:
        (HERE / "evidence" / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
