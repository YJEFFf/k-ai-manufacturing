"""Acquire public data from pinned primary distributions, without fitting models.

Python standard library only. Data/cache stay local; metadata is reviewable in Git.
Run from any directory: python acquire_data.py [--dataset core|nln]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parents[1]
YEJUN = HERE.parents[1]
REV = "b2c0d46c2971dcbfe71e26087b6d231998bb91c2"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 << 20), b""):
            h.update(b)
    return h.hexdigest()


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url, path, expected_sha=None, expected_bytes=None, hash_basis=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        partial = path.with_name(path.name + ".partial")
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as response, partial.open("wb") as out:
                    shutil.copyfileobj(response, out, length=4 << 20)
                if expected_bytes is not None and partial.stat().st_size != expected_bytes:
                    raise ValueError("Download length mismatch")
                if expected_sha and sha(partial) != expected_sha:
                    raise ValueError("Publisher SHA-256 mismatch")
                partial.replace(path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
    digest = sha(path)
    if expected_sha and digest != expected_sha:
        raise ValueError(f"SHA-256 mismatch: {path.name}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        raise ValueError(f"Size mismatch: {path.name}")
    return dict(url=url, path=str(path.relative_to(YEJUN)), bytes=path.stat().st_size,
                sha256=digest, checked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                hash_basis=hash_basis or "locally computed SHA-256; no independent expected hash",
                publisher_hash_verified=bool(expected_sha and hash_basis == "publisher metadata"))


def zip_inventory(path):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failed: {bad}")
        return [{"name": i.filename, "bytes": i.file_size, "crc32": f"{i.CRC:08x}"}
                for i in z.infolist() if not i.is_dir()]


def uci():
    old = YEJUN / "analysis/press_external/acquisition.json"
    prior = json.loads(old.read_text())
    path = old.parent / "data/hydraulic.zip"
    rec = fetch(prior["download"], path, prior["sha256"], prior["bytes"], "prior local acquisition receipt")
    rec.update(dataset="UCI Hydraulic", doi=prior["doi"], license="CC-BY-4.0",
               source=prior["source"], status="previously used; reverified, not a new holdout",
               crc_checked=True, members=zip_inventory(path), citation=prior["citation"])
    save_json(HERE / "evidence/uci_acquisition.json", rec)
    return {"dataset": "uci", "bytes": rec["bytes"], "files": len(rec["members"])}


def beihang():
    meta_url = "https://data.mendeley.com/public-api/datasets/xw8gjjk9km"
    meta_path = HERE / "cache/beihang_metadata.json"
    meta_receipt = fetch(meta_url, meta_path)
    meta = json.loads(meta_path.read_text())
    if meta["version"] != 1 or meta["doi"]["id"] != "10.17632/xw8gjjk9km.1":
        raise ValueError("Mendeley version changed; inspect before acquisition")
    if meta["data_licence"]["short_name"] != "CC BY 4.0":
        raise ValueError("Unexpected license")
    records = []
    for f in meta["files"]:
        d = f["content_details"]
        path = HERE / "data/beihang" / f["filename"]
        if path.parent != HERE / "data/beihang":
            raise ValueError("Unsafe filename")
        rec = fetch(d["download_url"], path, d["sha256_hash"], d["size"], "publisher metadata")
        rec.update(filename=f["filename"], file_id=f["id"], crc_checked=True,
                   members=zip_inventory(path))
        records.append(rec)
    result = dict(dataset="Beihang aviation piston pump", doi=meta["doi"]["id"],
                  source="https://data.mendeley.com/datasets/xw8gjjk9km/1",
                  license="CC-BY-4.0", metadata=meta_receipt, files=records,
                  citation="Ma, Jiming (2025), Experimental Data for Aviation Piston Pumps, Mendeley Data, V1, doi:10.17632/xw8gjjk9km.1",
                  creators=[f"{c['first_name']} {c['last_name']}" for c in meta["contributors"]],
                  license_url=meta["data_licence"]["url"],
                  changes="Original archive unchanged. Only healthy-run-1 timing/missingness and all CSV headers audited; no new model outcomes.",
                  access_scope="Archive acquired and CRC verified; no fitted model or test performance.")
    save_json(HERE / "evidence/beihang_acquisition.json", result)
    return {"dataset": "beihang", "bytes": sum(r["bytes"] for r in records),
            "members": sum(len(r["members"]) for r in records)}


def skab():
    reservation_path = HERE.parent / "press_unified_2026-10-02/evidence/skab_split_reservation.json"
    reservation = json.loads(reservation_path.read_text())
    assert reservation["revision"] == REV
    base = f"https://raw.githubusercontent.com/waico/SKAB/{REV}/"
    previous_path = HERE / "evidence/skab_acquisition.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    expected = {f["path"]: f for f in previous.get("files", []) + previous.get("notices", [])}
    def pinned_fetch(name):
        path = HERE / "data/skab" / name
        prior = expected.get(str(path.relative_to(YEJUN)), {})
        return fetch(base + name, path, prior.get("sha256"), prior.get("bytes"),
                     "pinned local receipt for immutable Git revision" if prior else None)
    notices = []
    for name in ["README.md", "LICENSE", "data/README.md"]:
        notices.append(pinned_fetch(name))
    def one(f):
        rec = pinned_fetch(f["path"])
        rec.update(split=f["split"], group=f["group"], source_path=f["path"],
                   inspection="acquisition is bytes/hash only; subsequent mechanical audits and final roles are recorded separately")
        return rec
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        records = list(ex.map(one, reservation["files"]))
    result = dict(dataset="SKAB", source="https://github.com/waico/SKAB", revision=REV,
                  license="GPL-3.0, as displayed by this pinned distribution; Kaggle is a separate distribution",
                  citation="Katser, Iurii D.; Kozitsin, Vyacheslav O. (2020), Skoltech Anomaly Benchmark (SKAB), doi:10.34740/KAGGLE/DSV/1693952",
                  reservation_sha256=sha(reservation_path), notices=notices, files=records,
                  split_scope="Historical file reservation at acquisition, superseded by evidence/skab_group_reservation.json. Run reserve_skab_groups.py before experiments.",
                  redistribution="Local research copy with original notices. Submission packaging must preserve applicable terms; no upstream model code imported.")
    save_json(HERE / "evidence/skab_acquisition.json", result)
    return {"dataset": "skab", "bytes": sum(r["bytes"] for r in records), "files": len(records)}


def nln():
    url = "https://data.4tu.nl/file/2b61183e-c14f-4131-829b-cc4822c369d0/8d84b13f-98f7-4baf-a7ea-60dee1e8876f"
    rec = fetch(url, HERE / "data/nln_emp/NLN-EMP-v4.7z", expected_bytes=20803099256)
    rec.update(dataset="NLN-EMP", doi="10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4",
               source="https://data.4tu.nl/datasets/2b61183e-c14f-4131-829b-cc4822c369d0/4",
               license="CC0-1.0", status="archive acquired; inspect member inventory before experimental use",
               citation="Bruinsma, S.; Geertsma, R.; Loendersloot, R.; Tinga, T. (2024), NLN-EMP, Version 4, 4TU.ResearchData.")
    save_json(HERE / "evidence/nln_acquisition.json", rec)
    return {"dataset": "nln", "bytes": rec["bytes"]}


def espset():
    meta_path = HERE / "cache/espset_metadata.json"
    receipt = fetch("https://data.mendeley.com/public-api/datasets/m268jsw339", meta_path)
    meta = json.loads(meta_path.read_text())
    if (meta["version"] != 3 or meta["doi"]["id"] != "10.17632/m268jsw339.3"
            or meta["data_licence"]["short_name"] != "CC BY 4.0"):
        raise ValueError("ESPset version/license changed; inspect before acquisition")
    records = []
    for file in meta["files"]:
        c = file["content_details"]
        path = HERE / "data/espset" / file["filename"]
        if path.parent != HERE / "data/espset":
            raise ValueError("Unsafe filename")
        rec = fetch(c["download_url"], path, c["sha256_hash"], c["size"], "publisher metadata")
        rec.update(members=zip_inventory(path), crc_checked=True)
        records.append(rec)
    save_json(HERE / "evidence/espset_acquisition.json", dict(
        dataset="ESPset", doi=meta["doi"]["id"], version=3, license="CC-BY-4.0",
        source="https://data.mendeley.com/datasets/m268jsw339/3", metadata=receipt,
        title=meta["name"], creators=[f"{c['first_name']} {c['last_name']}" for c in meta["contributors"]],
        license_url=meta["data_licence"]["url"], publish_date=meta.get("publish_date"),
        changes="Original ZIPs unchanged. Derived metadata/ID/label counts and whole-pump split reservation; no fitted model or feature statistics.",
        files=records, scope="archives acquired and CRC verified; no model fitted"))
    return {"dataset":"espset", "bytes":sum(r["bytes"] for r in records)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["core", "uci", "beihang", "skab", "espset", "nln"], default="core")
    args = ap.parse_args()
    jobs = [uci, beihang, skab, espset] if args.dataset == "core" else [globals()[args.dataset]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(job): job.__name__ for job in jobs}
        failed = []
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                print(json.dumps(future.result(), ensure_ascii=False), flush=True)
            except Exception as exc:
                failed.append(name)
                print(json.dumps({"dataset": name, "error": str(exc)}, ensure_ascii=False), flush=True)
        if failed:
            raise SystemExit("Failed: " + ", ".join(failed))
