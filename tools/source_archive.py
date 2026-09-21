"""Create a reviewed-source snapshot; include only catalogued reference PDFs."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parent.parent
TOP=('LICENSE','NOTICE','README.md','TRADEMARKS.md','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md','SECURITY.md','pyproject.toml','desktop.py','requirements-desktop.lock','requirements-test.lock','requirements-windows-cp313.hashed.lock','requirements-build.lock','pysidedeploy.spec')
TOP=(*TOP, 'requirements-build.hashed.lock')
DIRECTORIES=('gw_imposition','tests','tools','docs','.github','release')
SUFFIXES={'.py','.md','.json','.toml','.txt','.svg','.yml','.yaml','.ps1','.spec','.png'}

def source_files():
    files=[ROOT/name for name in TOP if (ROOT/name).is_file()]
    for name in DIRECTORIES:
        files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix in SUFFIXES and '__pycache__' not in p.parts and not p.name.endswith('.pyc'))
    manual_root=ROOT/'gw_imposition'/'resources'/'manuals'
    catalog=json.loads((manual_root/'catalog.json').read_text(encoding='utf-8'))
    for document in catalog['documents']:
        path=manual_root/document['filename']
        if path.parent.resolve()!=manual_root.resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=document['sha256']:
            raise ValueError('Bundled manual does not match reviewed catalog.')
        files.append(path)
    return sorted(set(files))

if __name__=='__main__':
    output=ROOT/'build'/'source-release';output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with zipfile.ZipFile(output/'gw-bleed-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            name=path.relative_to(ROOT).as_posix();data=path.read_bytes()
            archive.writestr(name,data);manifest.append({'path':name,'sha256':hashlib.sha256(data).hexdigest()})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Created local source snapshot with {len(manifest)} files. Review before publishing.')
