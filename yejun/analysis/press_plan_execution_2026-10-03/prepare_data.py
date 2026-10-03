"""Restore exact, hash-verified inputs without changing historical receipts."""
from pathlib import Path
import argparse
import concurrent.futures
import hashlib
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MASTER = HERE.parents[1] / "plans/press_master_2026-10-03"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, path, expected, post=None):
    if path.exists():
        raw = path.read_bytes()
    else:
        request = urllib.request.Request(url, data=post, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    if digest(raw) != expected:
        raise ValueError(f"Hash mismatch: {path.name}; received {len(raw)} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    return {"url": url, "path": str(path.relative_to(HERE)), "bytes": len(raw), "sha256": expected}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["press", "skab", "all"], default="all")
    args = parser.parse_args()
    receipts = []
    if args.dataset in ("press", "all"):
        source = json.loads((HERE.parent / "reselection/press_contest_audit.json").read_text(encoding="utf-8"))["source"]
        archive = HERE / "data/press.zip"
        receipts.append(fetch(source["url"], archive, source["archive_sha256"],
                              urllib.parse.urlencode({"fileSeq": source["post_fileSeq"]}).encode()))
        protocol = json.loads((MASTER / "protocol.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError("Archive CRC mismatch")
            for name, key in [("press_data_normal.csv", "normal_sha256"), ("outlier_data.csv", "abnormal_sha256")]:
                members = [i for i in z.infolist() if Path(i.filename).name == name]
                if len(members) != 1:
                    raise ValueError(f"Expected exactly one {name}")
                raw = z.read(members[0])
                if digest(raw) != protocol["input"][key]:
                    raise ValueError(f"Extracted input hash mismatch: {name}")
                dest = HERE / "data/press" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                receipts.append({"archive_member": members[0].filename, "path": str(dest.relative_to(HERE)),
                                 "sha256": digest(raw), "bytes": len(raw)})
    if args.dataset in ("skab", "all"):
        receipt = json.loads((MASTER / "evidence/skab_acquisition.json").read_text(encoding="utf-8"))
        def one(item):
            suffix = item["path"].replace("\\", "/").split("data/skab/", 1)[1]
            return fetch(item["url"], HERE / "data/skab" / suffix, item["sha256"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            receipts.extend(pool.map(one, receipt["files"] + receipt["notices"]))
    output = HERE / "evidence" / f"acquisition_{args.dataset}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"retrieved_utc": datetime.now(timezone.utc).isoformat(), "files": receipts},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dataset": args.dataset, "files": len(receipts), "verified": True}))


if __name__ == "__main__":
    main()
