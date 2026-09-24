"""Label-blind color-overlay removal, followed by separate ground-truth audit.

Prediction functions receive only pixels. Labels are used only to select a
training operating point and to score independently held-out acquisition dates.
The true pre-overlay grayscale image is unavailable: box coverage is NOT an
estimate of the number of actual foreign-body pixels destroyed.
"""
from pathlib import Path
import collections, hashlib, io, json, re, zipfile
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw

HERE=Path(__file__).parent
SOURCE=HERE/'images_labels_recovered.zip'

def remove_overlay(rgb, dilation=1):
    """No labels, filenames, boxes, or dataset split are arguments."""
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    chromatic=np.ptp(rgb,axis=2)>5
    mask=chromatic.copy()
    if dilation:
        mask=ndimage.binary_dilation(mask,structure=np.ones((3,3)),iterations=dilation)
    cleaned=cv2.inpaint(gray,np.uint8(mask)*255,3,cv2.INPAINT_TELEA)
    return gray,cleaned,chromatic,mask

def candidates(gray):
    """Fixed multiscale dark-spot generator; pixels only, no overlay mask."""
    a=gray.astype(np.float32)
    # Product interior from intensity alone; no annotated ROI is supplied.
    _,body=cv2.threshold(gray,0,1,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    body=ndimage.binary_erosion(body.astype(bool),iterations=3)
    scores=np.max([ndimage.gaussian_laplace(a,sigma=s)*s*s for s in (.7,1.,1.5,2.,3.,4.)],axis=0)
    peaks=(scores==ndimage.maximum_filter(scores,size=5)) & (scores>=3) & body
    peaks[:8]=False;peaks[-8:]=False;peaks[:,:8]=False;peaks[:,-8:]=False
    ys,xs=np.where(peaks)
    order=np.argsort(-scores[ys,xs],kind='stable')
    chosen=[]
    for k in order:
        x,y=int(xs[k]),int(ys[k]); score=float(scores[y,x])
        if all((x-q[0])**2+(y-q[1])**2>=64 for q in chosen):chosen.append([x,y,score])
        if len(chosen)>=100:break
    return chosen

def iou(b,q):
    b=np.asarray(b);q=np.asarray(q)
    inter=np.maximum(0,np.minimum(b[2:],q[2:])-np.maximum(b[:2],q[:2])).prod()
    union=np.maximum(0,b[2:]-b[:2]).prod()+np.maximum(0,q[2:]-q[:2]).prod()-inter
    return float(inter/union) if union else 0.

def score_rows(rows,variant,config,cutoff=.5):
    size,threshold,topk=config;tp=fp=fn=0;per=[]
    for r in rows:
        pred=[[x-size/2,y-size/2,x+size/2,y+size/2] for x,y,s in r['candidates'][variant] if s>=threshold][:topk]
        available=set(range(len(r['boxes'])));itp=0
        for b in pred:
            matches=[(iou(b,r['boxes'][j]),j) for j in available]
            if matches:
                best,j=max(matches)
                if best>=cutoff:available.remove(j);itp+=1
        ifp=len(pred)-itp;ifn=len(available);tp+=itp;fp+=ifp;fn+=ifn
        per.append({'stem':r['stem'],'tp':itp,'fp':ifp,'fn':ifn})
    return {'images':len(rows),'gt_boxes':tp+fn,'tp':tp,'fp':fp,'fn':fn,
        'precision':tp/(tp+fp) if tp+fp else 0.,'recall':tp/(tp+fn) if tp+fn else 0.,
        'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,'false_candidates_per_image':fp/len(rows) if rows else None,'per_image':per}

def summary(values):
    a=np.asarray(values,dtype=float)
    return {'n':len(a),'mean':float(np.mean(a)),'median':float(np.median(a)),
        'q90':float(np.quantile(a,.9)),'q95':float(np.quantile(a,.95)),'max':float(a.max()),
        'positive_count':int((a>0).sum()),'over_10pct_count':int((a>.1).sum()),'over_25pct_count':int((a>.25).sum()),'over_50pct_count':int((a>.5).sum())}

def main():
    rows=[];overlay_boxes=collections.defaultdict(list); changed_boxes=collections.defaultdict(list)
    image_metrics=[]; preview_records=[]
    with zipfile.ZipFile(SOURCE) as z:
        assert z.testzip() is None
        labels={Path(n).stem:z.read(n).decode('utf-8-sig') for n in z.namelist() if '라벨링 6종 세트/labels/' in n and n.endswith('.txt')}
        sources={}
        for n in z.namelist():
            if 'X선이물검출기' in n and Path(n).stem in labels and Path(n).suffix.lower() in {'.bmp','.jpg','.jpeg','.png'}:
                sources.setdefault(Path(n).stem,n)
        assert len(labels)==len(sources)==500
        with zipfile.ZipFile(HERE/'cleaned_d1_labeled_images.zip','w',compression=zipfile.ZIP_DEFLATED) as cleanzip:
            for idx,stem in enumerate(sorted(labels)):
                rgb=np.array(Image.open(io.BytesIO(z.read(sources[stem]))).convert('RGB'));h,w=rgb.shape[:2]
                # Removal happens before label parsing and never receives labels.
                variants={};im={'stem':stem,'width':w,'height':h,'variants':{}}
                for dilation in (0,1,2):
                    gray,clean,chroma,mask=remove_overlay(rgb,dilation)
                    variants[dilation]=(clean,mask)
                    grad=np.hypot(ndimage.sobel(clean.astype(float),axis=0),ndimage.sobel(clean.astype(float),axis=1))
                    oldgrad=np.hypot(ndimage.sobel(gray.astype(float),axis=0),ndimage.sobel(gray.astype(float),axis=1))
                    # This is an edge-trace diagnostic, not a certified artifact test.
                    im['variants'][str(dilation)]={'mask_pixels':int(mask.sum()),'image_fraction':float(mask.mean()),
                       'pixels_changed':int((clean!=gray).sum()),'outside_mask_changed':int(((clean!=gray)&~mask).sum()),
                       'mean_gradient_on_original_color':float(grad[chroma].mean()),
                       'original_mean_gradient_on_original_color':float(oldgrad[chroma].mean())}
                buf=io.BytesIO();Image.fromarray(variants[1][0]).save(buf,format='PNG');cleanzip.writestr(stem+'.png',buf.getvalue())
                boxes=[];boxrows=[]
                for line in labels[stem].strip().splitlines():
                    c,x,y,bw,bh=map(float,line.split());b=[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h];boxes.append(b)
                    x1,y1,x2,y2=b;sl=np.s_[max(0,int(np.floor(y1))):min(h,int(np.ceil(y2))),max(0,int(np.floor(x1))):min(w,int(np.ceil(x2)))]
                    br={'box':b,'width':bw*w,'height':bh*h,'coverage':{},'changed_fraction':{}}
                    for d,(clean,mask) in variants.items():
                        v=float(mask[sl].mean());q=float((clean[sl]!=gray[sl]).mean())
                        br['coverage'][str(d)]=v;br['changed_fraction'][str(d)]=q
                        overlay_boxes[d].append(v);changed_boxes[d].append(q)
                    boxrows.append(br)
                match=re.search(r'/([0-9]+)호기',sources[stem])
                r={'stem':stem,'source':sources[stem],'date':stem[4:12],'machine':match.group(1) if match else None,
                   'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),'boxes':boxes,'box_audit':boxrows,
                   'candidates':{'original_gray':candidates(gray),'cleaned_d1':candidates(variants[1][0])}}
                rows.append(r);image_metrics.append(im)
                if idx in (0,125,250,375,499):
                    # Full-image previews are for review only and never fed to prediction.
                    panels=[Image.fromarray(rgb),Image.fromarray(variants[0][0]).convert('RGB'),Image.fromarray(variants[1][0]).convert('RGB'),Image.fromarray(variants[2][0]).convert('RGB')]
                    canvas=Image.new('RGB',(w*4,h+24),'white');draw=ImageDraw.Draw(canvas)
                    for col,panel in enumerate(panels):canvas.paste(panel,(col*w,24));draw.text((col*w+4,4),['original','color-only mask','mask + 1 px','mask + 2 px'][col],fill='black')
                    pn=f'comparison_{idx:03d}.png';canvas.save(HERE/pn);preview_records.append({'stem':stem,'path':pn})
                if (idx+1)%50==0:print('processed',idx+1,flush=True)
    dates=sorted(set(r['date'] for r in rows));assert len(dates)==24
    partitions={'train':dates[:16],'validation':dates[16:19],'test':dates[19:]}
    splitrows={k:[r for r in rows if r['date'] in v] for k,v in partitions.items()}
    configs=[(s,t,k) for s in (6,10,14,18) for t in (3,5,8,12,20) for k in (3,5,10)]
    baselines={}
    for variant in ('original_gray','cleaned_d1'):
        ranked=sorted(((score_rows(splitrows['train'],variant,c)['f1'],c) for c in configs),reverse=True)
        best=ranked[0][1]
        baselines[variant]={'config_selected_only_on_first_16_dates':{'box_side_px':best[0],'min_log_score':best[1],'max_candidates':best[2]},
           'iou_0_5':{k:score_rows(v,variant,best,.5) for k,v in splitrows.items()},
           'iou_0_25_diagnostic':{k:score_rows(v,variant,best,.25) for k,v in splitrows.items()},
           'best_training_f1':ranked[0][0]}
    hashes={k:{r['rgb_sha256'] for r in v} for k,v in splitrows.items()}
    result={'source':str(SOURCE),'originals_modified':False,'label_free_removal':True,
      'removal':'RGB max-min>5; optional 3x3 dilation; grayscale Telea radius3; no GT inputs',
      'n_images':len(rows),'n_gt_boxes':sum(len(r['boxes']) for r in rows),'dates':partitions,
      'split_counts':{k:{'images':len(v),'boxes':sum(len(r['boxes']) for r in v),'machines':dict(collections.Counter(r['machine'] for r in v))} for k,v in splitrows.items()},
      'split_hash_overlaps':{a+'__'+b:len(hashes[a]&hashes[b]) for a in hashes for b in hashes if a<b},
      'box_mask_coverage':{str(k):summary(v) for k,v in overlay_boxes.items()},
      'box_pixels_changed_fraction':{str(k):summary(v) for k,v in changed_boxes.items()},
      'image_metrics':image_metrics,'baselines':baselines,'previews':preview_records,
      'limits':['No clean pre-overlay reference: occluded foreign-body signal cannot be recovered or measured directly.',
        'Grayscale output eliminates chroma by construction, not all learnable inpainting traces.',
        'All 500 labeled images contain boxes; real normal-production false rejection is not measured.',
        'Candidate FPs are relative to supplied annotations; completeness of annotations is not independently certified.',
        'Date split prevents exact-image reuse but not all product/lot dependencies.','This is a simple spot candidate baseline, not a trained object detector.']}
    (HERE/'cleaning_probe_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (HERE/'per_image_boxes_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in {'image_metrics','baselines'}},ensure_ascii=False,indent=2),flush=True)
    for var,res in baselines.items():
        print(var,res['config_selected_only_on_first_16_dates'],{k:{a:b for a,b in v.items() if a!='per_image'} for k,v in res['iou_0_5'].items()},flush=True)

if __name__=='__main__':main()
