"""Inspect every official TXT label, raw image identity and colored overlay."""
from pathlib import Path
import collections
import hashlib
import io
import json
import re
import zipfile
import numpy as np
from PIL import Image
from scipy import ndimage

HERE=Path(__file__).parent
ZIP=Path('/tmp/kamp-contest-originals/8080_image_label_recovered.zip')


def main():
    prefix=json.loads((HERE/'xray_prefix_audit.json').read_text())
    images=prefix['images']
    raw=[r for r in images if 'X선이물검출기' in r['name']]
    by_stem=collections.defaultdict(list)
    for r in raw:by_stem[Path(r['name']).stem].append(r)
    texts=prefix['text_files']
    labels={Path(n).stem:t for n,t in texts.items() if '라벨링 6종 세트/labels/' in n}
    repeated_labels=collections.defaultdict(list)
    for n,t in texts.items():
        if '/labels/' in n or '/YOLO_darknet/' in n:
            repeated_labels[Path(n).stem].append({'name':n,'text':t.strip()})
    conflicting=[{'stem':s,'versions':v} for s,v in repeated_labels.items() if len({x['text'] for x in v})>1]
    rows=[]
    all_hashes=collections.Counter(r['rgb_sha256'] for r in raw)
    with zipfile.ZipFile(ZIP) as z:
        assert z.testzip() is None
        for stem,t in labels.items():
            candidates=by_stem.get(stem,[])
            r={'stem':stem,'raw_matches':len(candidates),'boxes':[]}
            if not candidates:
                rows.append(r);continue
            imeta=candidates[0]
            a=np.array(Image.open(io.BytesIO(z.read(imeta['name']))).convert('RGB'))
            h,w=a.shape[:2]
            mask=a.max(axis=2)-a.min(axis=2)>5
            components,ncomp=ndimage.label(mask,structure=np.ones((3,3)))
            boxes_color=[]
            for sl in ndimage.find_objects(components):
                ys,xs=sl
                if (xs.stop-xs.start)*(ys.stop-ys.start)>=9:
                    boxes_color.append([xs.start,ys.start,xs.stop,ys.stop])
            for line in t.strip().splitlines():
                v=list(map(float,line.split()))
                c,x,y,bw,bh=v
                b=np.array([(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h])
                x1,y1,x2,y2=b
                crop=mask[max(0,int(y1)):min(h,int(np.ceil(y2))),max(0,int(x1)):min(w,int(np.ceil(x2)))]
                ious=[]
                center_inside=[]
                for q in boxes_color:
                    q=np.array(q);inter=np.maximum(0,np.minimum(b[2:],q[2:])-np.maximum(b[:2],q[:2])).prod()
                    union=(b[2:]-b[:2]).prod()+(q[2:]-q[:2]).prod()-inter
                    ious.append(float(inter/union) if union else 0.)
                    center_inside.append(bool(q[0]<=x*w<=q[2] and q[1]<=y*h<=q[3]))
                r['boxes'].append({'class':c,'width_px':bw*w,'height_px':bh*h,
                    'within_image':bool(0<=x1<x2<=w and 0<=y1<y2<=h),
                    'chromatic_fraction_in_box':float(crop.mean()) if crop.size else None,
                    'center_inside_color_component_rectangle':any(center_inside),
                    'best_color_component_iou':max(ious,default=0)})
            machine_match=re.search(r'/([0-9]+)호기',imeta['name'])
            r.update(rgb_sha256=imeta['rgb_sha256'],date=stem[4:12],filename_prefix=stem[:3],
                     machine_directory=machine_match.group(1) if machine_match else None,
                     raw_duplicate_count=all_hashes[imeta['rgb_sha256']],
                     color_components=len(boxes_color),chromatic_pixels=int(mask.sum()))
            rows.append(r)
    boxes=[b for r in rows for b in r['boxes']]
    rgb_groups=collections.defaultdict(list)
    for r in rows:
        if 'rgb_sha256' in r:rgb_groups[r['rgb_sha256']].append(r['stem'])
    labeled_hashes=set(rgb_groups)
    image_set_hashes=collections.defaultdict(set)
    for im in images:
        if '라벨링 6종 세트/images ' in im['name']:
            image_set_hashes[Path(im['name']).parent.name].add(im['rgb_sha256'])
    out={'source':'official contest attachment 8080; raw images/TXT recovered before unused checkpoint files',
         'recovered_zip_crc_all_pass':True,'raw_image_count':len(raw),'raw_unique_rgb':len(all_hashes),
         'raw_all_chromatic':all(r['chromatic_pixels']>0 for r in raw),
         'label_files_main':len(labels),'label_objects':len(boxes),'empty_label_files':sum(not t.strip() for t in labels.values()),
         'matched_label_files':sum(bool(r['raw_matches']) for r in rows),
         'labeled_unique_rgb':len(labeled_hashes),'labeled_duplicate_groups':[v for v in rgb_groups.values() if len(v)>1],
         'classes':dict(collections.Counter(str(b['class']) for b in boxes)),
         'out_of_bounds_boxes':sum(not b['within_image'] for b in boxes),
         'date_counts':dict(collections.Counter(r.get('date') for r in rows)),
         'machine_directory_counts':dict(collections.Counter(r.get('machine_directory') for r in rows)),
         'overlap_guide_image_sets':{f'{a} vs {b}':len(va&vb) for a,va in image_set_hashes.items() for b,vb in image_set_hashes.items() if a<b},
         'label_version_conflicts':conflicting,
         'objects_color_iou_ge_05':sum(b['best_color_component_iou']>=.5 for b in boxes),
         'objects_center_inside_color_rectangle':sum(b['center_inside_color_component_rectangle'] for b in boxes),
         'objects_with_chromatic_pixels':sum((b['chromatic_fraction_in_box'] or 0)>0 for b in boxes),
         'median_box_width_px':float(np.median([b['width_px'] for b in boxes])),
         'median_box_height_px':float(np.median([b['height_px'] for b in boxes])),
         'rows':rows}
    (HERE/'xray_label_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in out.items() if k not in ['rows','label_version_conflicts','labeled_duplicate_groups']},ensure_ascii=False,indent=2))
    print('label_conflicts',len(conflicting),'duplicate_labeled_groups',len(out['labeled_duplicate_groups']))


if __name__=='__main__':main()
