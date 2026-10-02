"""Re-fetch primary source pages and preserve receipts, not just citations."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.request

HERE = Path(__file__).resolve().parents[1]
REV = "b2c0d46c2971dcbfe71e26087b6d231998bb91c2"
SOURCES = [
    ("KAMP_NOTICE", "https://www.kamp-ai.kr/noticeDetail?NOTICE_SEQ=86", "official rules and submission requirements"),
    ("KAMP_DATA", "https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48", "official source description; does not establish ADC rate"),
    ("UCI", "https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems", "sensors, labels, CC BY 4.0"),
    ("SKAB_README", f"https://raw.githubusercontent.com/waico/SKAB/{REV}/README.md", "pinned sensor and label definitions"),
    ("SKAB_LICENSE", f"https://raw.githubusercontent.com/waico/SKAB/{REV}/LICENSE", "license of selected distribution"),
    ("SKAB_DATA", f"https://raw.githubusercontent.com/waico/SKAB/{REV}/data/README.md", "directory explanation; numbering discrepancy"),
    ("BEIHANG_META", "https://data.mendeley.com/public-api/datasets/xw8gjjk9km", "version, publisher checksum and CC BY 4.0"),
    ("BEIHANG_PAPER", "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12769818/fullTextXML", "author article, tables, limitations; not proof that files match"),
    ("NLN_META", "https://api.datacite.org/dois/10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4", "version, authors, CC0, article DOI"),
    ("NLN_PAGE", "https://data.4tu.nl/datasets/2b61183e-c14f-4131-829b-cc4822c369d0/4", "official distribution and file link"),
    ("AI4EU_META", "https://zenodo.org/api/records/5729187", "file inventory, attribution and license; no assumed health labels"),
    ("PHM_2022", "https://data.phmsociety.org/2022-phm-conference-data-challenge/", "task structure; inspect explicit dataset terms before use"),
    ("ESPSET_META", "https://data.mendeley.com/public-api/datasets/m268jsw339", "version, license, spectrum representation"),
    ("MIMII_META", "https://zenodo.org/api/records/4740355", "audio domain and NC-SA terms"),
    ("PADERBORN", "https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter/data-sets-and-download", "official download and usage terms"),
    ("FZU", "https://raw.githubusercontent.com/HuiHuang2025/FZU_HGPFD/main/README.md", "discovery only; institution and terms unresolved"),
    ("LONGTAIL_META", "https://data.mendeley.com/public-api/datasets/63gjxpn7s6", "discovery metadata; authorship/experimental units not yet validated"),
    ("CROSS_CONFORMAL", "https://arxiv.org/html/1208.0806", "early cross conformal method and lack of theorem in that note"),
    ("BEYOND_EXCHANGEABILITY", "https://arxiv.org/html/2202.13415", "theorems require method and assumption matching"),
    ("OUTLIER_P", "https://arxiv.org/abs/2104.08279", "conformal outlier p values, abstract/bibliography"),
    ("TSAD_EVAL", "https://arxiv.org/abs/2109.05257", "point adjustment critique, abstract/bibliography"),
    ("AUG_SURVEY", "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0254841", "augmentation benefits depend on task and method"),
    ("BLOCK_BOOTSTRAP", "https://api.crossref.org/works/10.1214/aos/1176347265", "bibliographic confirmation only; stationarity is not established here"),
    ("NIST_EWMA", "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm", "sequential monitoring background"),
    ("NIST_POISSON", "https://www.itl.nist.gov/div898/handbook/apr/section4/apr451.htm", "constant-rate zero-failure confidence planning assumptions"),
    ("GPL_FAQ", "https://www.gnu.org/licenses/gpl-faq.html", "copyleft is not a ban on commercial use; assess distribution separately"),
    ("CC_BY", "https://creativecommons.org/licenses/by/4.0/", "attribution, license link, changes"),
    ("CC_ZERO", "https://creativecommons.org/publicdomain/zero/1.0/", "CC0 scope"),
    ("SKLEARN_LICENSE", "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/COPYING", "code license, not data license"),
]


def one(item):
    key, url, purpose = item
    row=dict(id=key,url=url,scope=purpose,checked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=35) as response:
            data=response.read()
            row.update(status=response.status,resolved_url=response.url,content_type=response.headers.get("Content-Type"))
        path=HERE/"cache/sources"/key
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),local_cache=str(path.relative_to(HERE)))
    except Exception as exc:
        row.update(status="unavailable",error=str(exc))
    return row


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(one,SOURCES))
    out=HERE/"evidence/source_receipts.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps([{k:r.get(k) for k in ["id","status","bytes","error"]} for r in rows],ensure_ascii=False,indent=2))
