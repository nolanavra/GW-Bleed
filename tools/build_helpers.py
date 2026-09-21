"""Acquire the exact native inspection helper used by this internal build."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen

URL = 'https://dependencywalker.com/depends22_x64.zip'
SHA256 = '35db68a613874a2e8c1422eb0ea7861f825fc71717d46dabf1f249ce9634b4f1'


def acquire(cache, evidence):
    target = Path(cache)/'downloads/depends/x86_64/depends22_x64.zip'
    if not target.exists():
        with urlopen(URL, timeout=60) as response:
            data = response.read(2*1024*1024)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError('Dependency inspection download checksum mismatch.')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
        raise ValueError('Cached dependency inspection helper checksum mismatch.')
    Path(evidence).write_text(json.dumps({'url':URL,'sha256':SHA256,'role':'Build-only native dependency inspection'},indent=2)+'\n')


if __name__=='__main__':
    acquire(sys.argv[1],sys.argv[2])
