"""Resolve original local CSVs or losslessly compressed deployment copies."""
from pathlib import Path
from functools import lru_cache
import hashlib
import json
import shutil
import tempfile


@lru_cache(maxsize=8)
def assemble_parts(manifest_path, modified_ns, manifest_size):
    manifest=Path(manifest_path)
    spec=json.loads(manifest.read_text(encoding='utf-8'))
    cache=Path(tempfile.gettempdir())/'event_dashboard_data'
    cache.mkdir(exist_ok=True)
    target=cache/(spec['sha256']+'.csv.gz')
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    if target.is_file() and target.stat().st_size==spec['size'] and digest(target)==spec['sha256']:
        return target
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=cache,delete=False) as output:
            temporary=Path(output.name)
            for part in spec['parts']:
                source=manifest.parent/part['name']
                if source.resolve().parent!=manifest.parent.resolve():
                    raise ValueError('Invalid data-part path')
                if source.stat().st_size!=part['size'] or digest(source)!=part['sha256']:
                    raise ValueError('Data part failed integrity check: '+part['name'])
                with source.open('rb') as stream:shutil.copyfileobj(stream,output,1024*1024)
        if temporary.stat().st_size!=spec['size'] or digest(temporary)!=spec['sha256']:
            raise ValueError('Reassembled data failed integrity check')
        temporary.replace(target)
        return target
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def processed_file(root, name):
    csv = Path(root) / 'data' / 'processed' / name
    compressed = csv.with_name(csv.name + '.gz')
    if csv.is_file():
        return csv
    if compressed.is_file():
        return compressed
    parts=compressed.with_name(compressed.name+'.parts.json')
    if parts.is_file():
        stat=parts.stat()
        return assemble_parts(str(parts.resolve()),stat.st_mtime_ns,stat.st_size)
    # Existing callers retain their helpful missing-file messages.
    return csv
