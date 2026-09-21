"""Build-specific dependency inventory and verbatim wheel license collection."""
import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import shutil
import sys

ROOT=Path(__file__).resolve().parent.parent

def inventory(output, lock):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    runtime_license=Path(sys.base_prefix)/'LICENSE.txt'
    if runtime_license.is_file():
        target=output/'third-party'/'CPython'/'LICENSE.txt'
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(runtime_license,target)
    packages=[]
    for line in Path(lock).read_text(encoding='utf-8-sig').splitlines():
        if not line or line.startswith(('#','-')): continue
        name,version=line.split('==');dist=distribution(name)
        if dist.version!=version: raise RuntimeError(f'{name}: expected {version}, installed {dist.version}')
        notices=[]
        for entry in dist.files or []:
            low=str(entry).lower()
            if not any(word in low for word in ('license','copying','notice','copyright')): continue
            source=Path(dist.locate_file(entry))
            if not source.is_file(): continue
            # Preserve complete paths to distinguish native component notices.
            relative=Path(name)/Path(*[part for part in Path(str(entry)).parts if part not in ('..','.','')])
            target=output/'third-party'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            notices.append({'path':str(Path('third-party')/relative).replace('\\','/'),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        packages.append({'name':name,'version':version,'license_expression':dist.metadata.get('License-Expression'),
                         'license_metadata':dist.metadata.get('License'),'notices':notices})
    record={'format':'GW dependency inventory 1','python':platform.python_version(),'platform':platform.platform(),'packages':packages,
            'review_status':'Inventory only; native/runtime license review remains required.'}
    (output/'dependency-inventory.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='build/release-evidence');parser.add_argument('--lock',default=str(ROOT/'requirements-desktop.lock'));args=parser.parse_args()
    result=inventory(args.output,args.lock);print(f"Inventoried {len(result['packages'])} desktop packages; copied available notices.")
