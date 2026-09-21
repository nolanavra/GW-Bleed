"""Snapshot, prepare and assemble a traceable internal standalone build."""
import argparse
import configparser
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')


def snapshot(run):
    from source_archive import source_files
    target = run/'source'
    target.mkdir(parents=True, exist_ok=False)
    manifest = []
    for path in source_files():
        relative = path.relative_to(ROOT)
        dest = target/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        manifest.append({'path': relative.as_posix(), 'sha256': digest(dest)})
    source_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    git = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, text=True)
    write_json(run/'source-manifest.json', {'snapshot': source_hash, 'files': manifest,
               'git_revision': git.stdout.strip() if git.returncode == 0 else None,
               'note': 'Captured files include working changes; snapshot hash is authoritative.'})
    return target


def prepare(run):
    from PIL import Image
    source = run/'source'
    info = json.loads((run/'source-manifest.json').read_text())
    version = tomllib.loads((source/'pyproject.toml').read_text())['project']['version']
    build_info = {'version': version, 'channel': 'Internal alpha — unverified machine profiles',
                  'source_snapshot': info['snapshot'], 'signed': False,
                  'python': platform.python_version(), 'built_utc': datetime.now(timezone.utc).isoformat()}
    write_json(source/'gw_imposition/resources/build-info.json', build_info)
    icon = source/'build/alpha.ico'
    icon.parent.mkdir(exist_ok=True)
    with Image.open(source/'gw_imposition/resources/GW BLEED ICON.png') as image:
        image.convert('RGBA').save(icon, sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    cfg = configparser.ConfigParser()
    cfg.read(source/'pysidedeploy.spec')
    cfg['app']['project_dir'] = str(source)
    cfg['app']['input_file'] = str(source/'desktop.py')
    cfg['app']['exec_directory'] = str(source/'build/standalone')
    cfg['app']['icon'] = str(icon)
    cfg['python']['python_path'] = sys.executable
    with (source/'pysidedeploy.spec').open('w') as stream:
        cfg.write(stream)
    freeze = subprocess.check_output([sys.executable,'-m','pip','freeze'], text=True)
    (run/'installed-packages.txt').write_text(freeze, encoding='utf-8')
    write_json(run/'build-info.json', build_info)


def tests(run):
    with (run/'regression-tests.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable,'tools/run_tests.py'], cwd=run/'source',
                                stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('Regression tests failed. See regression-tests.log.')


def assemble(run):
    source = run/'source'
    report = ET.parse(source/'build/nuitka-report.xml').getroot()
    if report.get('completion') != 'yes':
        raise RuntimeError('Nuitka did not report successful compilation; no package will be assembled.')
    executables = list((source/'build/standalone').glob('*.dist/GW-Bleed-Alpha.exe'))
    if len(executables) != 1:
        raise RuntimeError(f'Expected one complete Nuitka .dist folder, found {len(executables)}.')
    package = run/'package'/'GW Bleed Alpha'
    (run/'assembly-tools').mkdir(exist_ok=True)
    shutil.copyfile(__file__, run/'assembly-tools/alpha_build.py')
    write_json(run/'assembly-tool.json', {'sha256': digest(Path(__file__))})
    shutil.copytree(executables[0].parent, package)
    resources = package/'gw_imposition/resources'
    catalog = json.loads((resources/'manuals/catalog.json').read_text())
    for doc in catalog['documents']:
        if digest(resources/'manuals'/doc['filename']) != doc['sha256']:
            raise RuntimeError('Packaged manual checksum mismatch.')
    for forbidden in ('pymupdf','fitz','reportlab','pytest','zxingcpp','tests'):
        if any(forbidden in p.name.lower() for p in package.rglob('*')):
            raise RuntimeError(f'Unexpected development/legacy dependency: {forbidden}')
    for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','TRADEMARKS.md'):
        shutil.copyfile(source/name, package/name)
    shutil.copytree(source/'build/release-evidence', package/'licenses')
    shutil.copyfile(source/'docs/internal-alpha-testing.md', package/'START-HERE.md')
    shutil.copyfile(run/'build-info.json', package/'build-info.json')
    write_json(run/'clean-windows-acceptance.json', {'status': 'pending', 'windows_build': None,
        'artifact_sha256': None, 'reviewer': None, 'results': [],
        'reason': 'Requires a fresh Windows VM without development dependencies; local tests are insufficient.'})
    return package


def archive(run):
    package = run/'package'/'GW Bleed Alpha'
    smoke = json.loads((run/'packaged-worker-results.json').read_text())
    if smoke['status'] != 'passed':
        raise RuntimeError('Packaged smoke tests must pass before creating ZIP.')
    workflow = json.loads((run/'packaged-workflow-results.json').read_text())
    if workflow['status'] != 'passed':
        raise RuntimeError('Compiled GUI workflow checks must pass before creating ZIP.')
    manifest = [{'path': p.relative_to(package).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}
                for p in sorted(package.rglob('*')) if p.is_file()]
    write_json(run/'distribution-manifest.json', manifest)
    version = json.loads((run/'build-info.json').read_text())['version']
    target = run/f'GW-Bleed-{version}-windows-x64-alpha.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for row in manifest:
            z.write(package/row['path'], 'GW Bleed Alpha/'+row['path'])
    (run/(target.name+'.sha256')).write_text(digest(target)+'  '+target.name+'\n', encoding='ascii')
    acceptance = json.loads((run/'clean-windows-acceptance.json').read_text())
    acceptance['artifact_sha256'] = digest(target)
    write_json(run/'clean-windows-acceptance.json', acceptance)
    print(target)


def verify_zip(run):
    target = next(run.glob('*.zip'))
    manifest = json.loads((run/'distribution-manifest.json').read_text())
    with tempfile.TemporaryDirectory(prefix='GW alpha relocation ') as temp:
        root = Path(temp)/'Unicode \u03a9'
        with zipfile.ZipFile(target) as z:
            if z.testzip() is not None or set(z.namelist()) != {'GW Bleed Alpha/'+r['path'] for r in manifest}:
                raise RuntimeError('ZIP integrity or manifest membership failed.')
            z.extractall(root)
        package = root/'GW Bleed Alpha'
        for row in manifest:
            if digest(package/row['path']) != row['sha256']:
                raise RuntimeError('Extracted distribution hash mismatch.')
        env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
        env['PATH'] = str(Path(os.environ['WINDIR'])/'System32')
        result = subprocess.run([str(package/'GW-Bleed-Alpha.exe'),'--gw-worker','pdf',
            str(package/'samples/sample-artwork.pdf'),'1'], cwd=temp,env=env,
            capture_output=True,text=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        response = json.loads(result.stdout)
        if result.returncode or response.get('index') != 1 or not response.get('png'):
            raise RuntimeError('Relocated packaged worker failed.')
        renamed = package/'GW Bleed relocated.exe'
        (package/'GW-Bleed-Alpha.exe').rename(renamed)
        report = run/'relocated-workflow-results.json'
        result = subprocess.run([str(renamed), '--gw-check-workflow',
            str(package/'samples/sample-artwork.pdf'), str(report)], cwd=temp, env=env,
            capture_output=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or json.loads(report.read_text())['status'] != 'passed':
            raise RuntimeError('Relocated/renamed GUI workflow failed; see relocated-workflow-results.json.')
    write_json(run/'zip-verification.json', {'status':'passed','file_count':len(manifest),
        'archive_sha256':digest(target),'checks':['ZIP CRC','Extracted file hashes','Relocated Unicode-path worker without Python on PATH',
        'Relocated and renamed GUI preview, calculation and exports without Python on PATH'],
        'verification_tool_sha256': digest(Path(__file__))})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('snapshot','tests','prepare','assemble','archive','verify_zip'))
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    globals()[args.action](args.run.resolve())
