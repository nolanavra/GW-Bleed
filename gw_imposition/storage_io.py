"""Bounded reads and atomic replacement for user-owned configuration files."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

MAX_LAYOUT_BYTES = 16 * 1024 * 1024


def read_json(path, limit=MAX_LAYOUT_BYTES):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('Configuration file exceeds the supported size limit.')
    try:
        return json.loads(raw)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('Invalid or excessively nested configuration.') from exc


def fingerprint(path):
    path=Path(path)
    if not path.exists(): return None
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    stat=path.stat()
    return (stat.st_size, stat.st_mtime_ns, digest.hexdigest())


def atomic_json(path, data):
    path=Path(path)
    handle, temporary=tempfile.mkstemp(prefix='.gw-layout-', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf-8') as stream:
            json.dump(data,stream,indent=2,ensure_ascii=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)
