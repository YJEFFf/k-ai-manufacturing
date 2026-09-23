"""Read only public contest 8080 image/label entries; omit all model weights.

The recovered ZIP is a derived subset, not a complete copy of the source archive.
Every retained entry passes its original local-header CRC/size checks.
"""
from pathlib import Path
import argparse, hashlib, json, struct, time, urllib.parse, urllib.request, zipfile, zlib

OUT = Path(__file__).parent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=480)
    args = ap.parse_args()
    req = urllib.request.Request('https://www.kamp-ai.kr/cptFileDownload',
        data=urllib.parse.urlencode({'fileSeq':'8080'}).encode(),
        headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.kamp-ai.kr/contestNotice?noticeSeq=28'})
    deadline = time.monotonic() + args.seconds
    records=[]; offset=0; stop=None
    with urllib.request.urlopen(req, timeout=20) as response, zipfile.ZipFile(OUT/'images_labels_recovered.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as recovered:
        print('HTTP',response.status,'length',response.headers.get('Content-Length'),flush=True)
        pending=bytearray()
        def read(n):
            nonlocal offset
            while len(pending)<n:
                if time.monotonic()>deadline: raise TimeoutError('bounded download time exceeded')
                part=response.read(min(65536,n-len(pending)))
                if not part: raise EOFError('incomplete archive entry')
                pending.extend(part)
            part=bytes(pending[:n]);del pending[:n];offset+=n
            return part
        def unread(s):
            nonlocal offset
            pending[:0]=s;offset-=len(s)
        try:
            while offset < 450*1024*1024:
                pos=offset; h=read(30)
                if h[:4]!=b'PK\x03\x04':
                    stop={'offset':pos,'header':h[:4].hex()};break
                _,ver,flags,method,_,_,crc_h,csize_h,usize_h,nl,xl=struct.unpack('<IHHHHHIIIHH',h)
                name=read(nl).decode('utf-8' if flags&2048 else 'cp949');read(xl)
                if '/실습별 가중치파일/' in name or Path(name).suffix.lower() in {'.weights','.pth','.h5'}:
                    stop={'offset':pos,'name':name,'reason':'weights_omitted'};break
                ext=Path(name).suffix.lower(); retain=ext in {'.bmp','.jpg','.jpeg','.png','.txt','.names','.cfg'}
                buf=bytearray();crc=0;size=0;sha=hashlib.sha256();start=offset
                decoder=zlib.decompressobj(-15) if method==8 else None
                if method not in (0,8):raise ValueError(f'unsupported ZIP compression {method}')
                remaining=csize_h
                while (flags&8 and decoder and not decoder.eof) or remaining:
                    n=65536 if flags&8 else min(65536,remaining)
                    chunk=read(n);raw=decoder.decompress(chunk) if decoder else chunk
                    if not flags&8:remaining-=len(chunk)
                    crc=zlib.crc32(raw,crc);size+=len(raw);sha.update(raw)
                    if retain:buf.extend(raw)
                    if decoder and decoder.eof:
                        unread(decoder.unused_data);break
                compressed=offset-start
                if flags&8:
                    d=read(4)
                    if d==b'PK\x07\x08':d=read(4)
                    crc_h=struct.unpack('<I',d)[0];csize_h,usize_h=struct.unpack('<II',read(8))
                if (crc&0xffffffff,size,compressed)!=(crc_h,usize_h,csize_h):raise ValueError('CRC/size mismatch')
                records.append({'name':name,'bytes':size,'compressed_bytes':compressed,'sha256':sha.hexdigest(),'retained':retain,'crc_pass':True})
                if retain:recovered.writestr(name,buf)
                if len(records)%500==0:print('entries',len(records),'MB',round(offset/1024/1024,1),flush=True)
        except Exception as e:
            stop={'offset':offset,'error':repr(e)}
    result={'source':'public contest attachment fileSeq=8080','network_bytes_consumed':offset,'stop':stop,'entries':records,'complete_original_archive':False}
    (OUT/'recovery_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('DONE',len(records),offset,stop,flush=True)

if __name__=='__main__':main()
