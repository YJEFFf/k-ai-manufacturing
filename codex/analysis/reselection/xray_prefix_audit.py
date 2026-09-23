"""Inspect complete local ZIP entries while a public download is in progress.

Each accepted entry must pass its CRC and byte length. An incomplete final entry
is not counted as valid. A central-directory audit is still required at the end.
"""
from pathlib import Path
import collections
import hashlib
import io
import json
import struct
import zlib
import zipfile
import numpy as np
from PIL import Image

ZIP = Path('/tmp/kamp-contest-originals/8080.zip')
OUT = Path(__file__).parent


def audit():
    records, images, labels, samples = [], [], {}, []
    stop = None
    recovered_path = ZIP.with_name('8080_image_label_recovered.zip')
    recovered = zipfile.ZipFile(recovered_path, 'w', compression=zipfile.ZIP_DEFLATED)
    with ZIP.open('rb') as f:
        while True:
            pos = f.tell()
            h = f.read(30)
            if len(h) < 30 or h[:4] != b'PK\x03\x04':
                stop = {'offset': pos, 'header': h[:4].hex()}
                break
            _, ver, flags, method, _, _, crc_h, csize_h, usize_h, nl, xl = struct.unpack('<IHHHHHIIIHH',h)
            name = f.read(nl).decode('utf-8' if flags & 2048 else 'cp949')
            f.read(xl)
            if '/실습별 가중치파일/' in name:
                stop = {'offset': pos, 'name': name, 'reason': 'image_and_label_members_complete; unused_model_weights_omitted'}
                break
            start = f.tell()
            ext = Path(name).suffix.lower()
            retain = ext in {'.bmp','.jpg','.jpeg','.png','.txt','.names','.cfg'}
            buf = bytearray()
            crc, size, sha = 0, 0, hashlib.sha256()
            decoder = zlib.decompressobj(-15) if method == 8 else None
            remaining = csize_h
            try:
                if method not in (0,8):
                    raise ValueError('unsupported method')
                while (flags & 8 and decoder and not decoder.eof) or remaining:
                    n = 65536 if flags & 8 else min(65536,remaining)
                    chunk = f.read(n)
                    if not chunk:
                        raise EOFError('incomplete entry')
                    raw = decoder.decompress(chunk) if decoder else chunk
                    if not flags & 8:
                        remaining -= len(chunk)
                    crc = zlib.crc32(raw,crc);size += len(raw);sha.update(raw)
                    if retain:
                        buf.extend(raw)
                    if decoder and decoder.eof:
                        f.seek(-len(decoder.unused_data),1)
                        break
                compressed = f.tell()-start
                if flags & 8:
                    d = f.read(4)
                    if d == b'PK\x07\x08':
                        d=f.read(4)
                    crc_h=struct.unpack('<I',d)[0]
                    csize_h,usize_h=struct.unpack('<II',f.read(8))
                if (crc & 0xffffffff,size,compressed) != (crc_h,usize_h,csize_h):
                    raise ValueError('CRC/size mismatch')
            except Exception as exc:
                stop={'offset':pos,'name':name,'error':str(exc)}
                break
            r={'name':name,'bytes':size,'compressed_bytes':compressed,'sha256':sha.hexdigest(),'crc_pass':True}
            records.append(r)
            if retain:
                recovered.writestr(name, buf)
            if ext in {'.bmp','.jpg','.jpeg','.png'}:
                try:
                    im=Image.open(io.BytesIO(buf));im.load();a=np.asarray(im.convert('RGB'))
                    chromatic=a.max(axis=2)-a.min(axis=2)>5
                    gray=np.asarray(im.convert('L'))
                    ir={'name':name,'width':im.width,'height':im.height,'mode':im.mode,
                        'rgb_sha256':hashlib.sha256(a.tobytes()).hexdigest(),
                        'gray_sha256':hashlib.sha256(gray.tobytes()).hexdigest(),
                        'chromatic_pixels':int(chromatic.sum()),'pixels':int(im.width*im.height)}
                    images.append(ir)
                    if ext=='.bmp' and chromatic.any() and len(samples)<4:
                        p=Path('/tmp')/f'kamp_xray_raw_{len(samples)}.bmp';p.write_bytes(buf);samples.append(str(p))
                except Exception as exc:
                    images.append({'name':name,'error':str(exc)})
            elif ext in {'.txt','.names','.cfg'}:
                try:labels[name]=buf.decode('utf-8-sig')
                except UnicodeDecodeError:labels[name]=buf.decode('cp949',errors='replace')
            if len(records)%500==0:
                print('verified',len(records),'images',len(images),'MB',f.tell()//1024//1024,flush=True)
    recovered.close()
    result={'zip_size_at_finish':ZIP.stat().st_size,'verified_entries':len(records),'stop':stop,
            'recovered_images_labels_zip': str(recovered_path),
            'members':records,'images':images,'text_files':labels,'samples':samples}
    (OUT/'xray_prefix_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('DONE',len(records),len(images),len(labels),stop,flush=True)


if __name__=='__main__':audit()
