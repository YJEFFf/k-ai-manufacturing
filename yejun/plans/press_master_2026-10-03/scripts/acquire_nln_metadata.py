"""Fetch NLN-EMP v4 directory and two documents using HTTP ranges.

Requires py7zr==1.1.3. Does not acquire the 20.8 GB nested sensor archive.
Sparse temporary archive is only an index carrier, never reported as real data.
"""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import urllib.request
import zlib

import py7zr

HERE=Path(__file__).resolve().parents[1]
URL="https://data.4tu.nl/file/2b61183e-c14f-4131-829b-cc4822c369d0/8d84b13f-98f7-4baf-a7ea-60dee1e8876f"
SIZE=20803099256
TARGETS=["README.txt","Appendices/Other/measurement overview.xlsx"]


def get_range(start,end):
    req=urllib.request.Request(URL,headers={"Range":f"bytes={start}-{end}"})
    with urllib.request.urlopen(req,timeout=60) as response:
        if response.status!=206 or response.headers.get("Content-Range")!=f"bytes {start}-{end}/{SIZE}":
            raise ValueError("Unexpected range/version")
        data=response.read()
    if len(data)!=end-start+1:
        raise ValueError("Incomplete range")
    return data


def main():
    h=get_range(0,31)
    if h[:6]!=b"7z\xbc\xaf\x27\x1c" or zlib.crc32(h[12:])!=struct.unpack("<I",h[8:12])[0]:
        raise ValueError("Archive start-header mismatch")
    offset,length,crc=struct.unpack("<QQI",h[12:])
    tail=get_range(SIZE-1048576,SIZE-1)
    tail_start=offset+32-(SIZE-1048576)
    if zlib.crc32(tail[tail_start:tail_start+length])!=crc:
        raise ValueError("Next-header CRC mismatch")
    first_block=get_range(32,5159679)
    with tempfile.TemporaryDirectory(prefix="press-nln-index-") as temp:
        index=Path(temp)/"index.7z"
        with index.open("wb") as stream:
            stream.write(h)
            stream.seek(32);stream.write(first_block)
            stream.seek(SIZE-len(tail));stream.write(tail)
        out=HERE/"data/nln_emp/metadata"
        out.mkdir(parents=True,exist_ok=True)
        with py7zr.SevenZipFile(index) as archive:
            info=archive.archiveinfo()
            files=[dict(name=f.filename,uncompressed=f.uncompressed,compressed=f.compressed,is_directory=f.is_directory) for f in archive.files]
            # The XLSX has a Windows reparse flag despite containing regular ZIP
            # document bytes. Normalize attributes only for these two fixed paths.
            for f in archive.files:
                if f.filename in TARGETS:
                    f._file_info["attributes"]=32
            archive.extract(path=out,targets=TARGETS)
        if not (out/TARGETS[1]).read_bytes().startswith(b"PK"):
            raise ValueError("Unexpected spreadsheet format")
        inventory=dict(source=URL,doi="10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4",
                       scope="Range-fetched directory only; sensor archive not acquired",archive_bytes=SIZE,
                       solid=info.solid,blocks=info.blocks,uncompressed=info.uncompressed,files=files)
        receipt=dict(source=URL,doi=inventory["doi"],license="CC0-1.0",
                     scope="Range-fetched archive index and first block; only two metadata documents extracted. Fixed target reparse attributes cleared in memory, content unchanged.",
                     transferred_ranges_bytes=len(h)+len(tail)+len(first_block),
                     files=[dict(path=str((out/t).relative_to(HERE)),bytes=(out/t).stat().st_size,
                                 sha256=hashlib.sha256((out/t).read_bytes()).hexdigest()) for t in TARGETS])
        for name,obj in [("nln_archive_inventory.json",inventory),("nln_metadata_acquisition.json",receipt)]:
            (HERE/"evidence"/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
