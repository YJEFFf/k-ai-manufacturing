"""Inspect safety annotations from an incomplete EGG without disk extraction."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zlib

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
scan_path = next(HERE.glob("*32652.egg_scan.json"))
scan = json.loads(scan_path.read_text())
entries = scan["entries"]
source = ROOT / scan["archive"]
out = {
    "archive": scan["archive"],
    "status": "incomplete EGG: metadata and complete annotation blocks only",
    "directories": dict(Counter(str(Path(e["filename"]).parent) for e in entries)),
}
splits = defaultdict(set)
images = defaultdict(set)
clips = defaultdict(Counter)
labels = Counter()
dimensions = Counter()
objects_per_annotation = Counter()
bad_boxes = []
missing_names = []
xml_errors = []
image_samples = []


def unpack(f, e):
    f.seek(e["block_data_offset"])
    data = f.read(e["compressed_size"])
    if len(data) != e["compressed_size"]:
        raise ValueError("truncated payload")
    if e["compress_method"] == 1:
        raw = zlib.decompress(data, -15)
    elif e["compress_method"] == 0:
        raw = data
    else:
        raise ValueError(f"unsupported method {e['compress_method']}")
    assert len(raw) == e["uncompressed_size"]
    assert zlib.crc32(raw) & 0xffffffff == e["crc32"]
    return raw


with source.open("rb") as f:
    for e in entries:
        p = Path(e["filename"])
        split = p.parent.name.replace("_annot", "").replace("_image", "")
        if p.suffix.lower() == ".xml":
            splits[split].add(p.stem)
            clip = re.sub(r"_\d+$", "", p.stem)
            clips[split][clip] += 1
            try:
                root = ET.fromstring(unpack(f, e))
                w = int(root.findtext("size/width"))
                h = int(root.findtext("size/height"))
                dimensions[f"{w}x{h}"] += 1
                objects = root.findall("object")
                objects_per_annotation[len(objects)] += 1
                for o in objects:
                    labels[o.findtext("name")] += 1
                    b = o.find("bndbox")
                    box = [float(b.findtext(c)) for c in ("xmin", "ymin", "xmax", "ymax")]
                    if not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h):
                        bad_boxes.append(dict(file=p.name, box=box, size=[w, h]))
                xml_image = root.findtext("filename")
                if xml_image and Path(xml_image).stem != p.stem:
                    missing_names.append([p.name, xml_image])
            except Exception as ex:
                xml_errors.append([p.name, repr(ex)])
        elif p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            images[split].add(p.stem)
            if len(image_samples) < 3:
                try:
                    raw = unpack(f, e)
                    im = Image.open(io.BytesIO(raw))
                    im.load()
                    image_samples.append({"file": e["filename"], "size": list(im.size), "mode": im.mode,
                                          "sha256": hashlib.sha256(raw).hexdigest()})
                except Exception as ex:
                    image_samples.append({"file": e["filename"], "error": repr(ex)})

out.update({
    "labels": dict(labels), "dimensions": dict(dimensions),
    "objects_per_annotation": dict(objects_per_annotation),
    "bad_boxes_count": len(bad_boxes), "bad_boxes_examples": bad_boxes[:10],
    "xml_errors": xml_errors, "xml_filename_mismatch_count": len(missing_names),
    "annotation_splits": {k: len(v) for k, v in splits.items()},
    "image_header_splits": {k: len(v) for k, v in images.items()},
    "clip_counts": {k: dict(v) for k, v in clips.items()},
    "sample_decoded_images": image_samples,
})
names = list(splits)
out["split_intersections"] = []
for i, a in enumerate(names):
    for b in names[i+1:]:
        ca, cb = set(clips[a]), set(clips[b])
        out["split_intersections"].append({"splits": [a, b],
            "identical_annotation_stems": len(splits[a] & splits[b]),
            "shared_video_prefixes": len(ca & cb), "prefixes": sorted(ca & cb),
            "a_clip_count": len(ca), "b_clip_count": len(cb)})
out["image_pairing"] = {k: {
    "annotation_without_image_header": len(v - images.get(k, set())),
    "image_header_without_annotation": len(images.get(k, set()) - v),
} for k, v in splits.items()}
frame_sets = defaultdict(lambda: defaultdict(set))
for split, stems in splits.items():
    for stem in stems:
        prefix, frame = stem.rsplit("_", 1)
        if frame.isdigit():
            frame_sets[split][prefix].add(int(frame))
nearest = Counter()
for prefix, frames in frame_sets.get("valid", {}).items():
    train_frames = frame_sets.get("train", {}).get(prefix, set())
    if train_frames:
        nearest.update(min(abs(f - t) for t in train_frames) for f in frames)
out["valid_nearest_train_frame_index_distance"] = dict(nearest)
dest = HERE / "energy_vision" / "raw29.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in out.items() if k != "clip_counts"}, ensure_ascii=False, indent=2))
