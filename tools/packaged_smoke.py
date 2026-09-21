"""Exercise compiled workers, never a Python worker, from an unrelated directory."""
import base64
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gw_imposition.models import Job, Margins
from gw_imposition.profiles import load_profile
from gw_imposition.layout_engine import calculate
from gw_imposition.registration import RegistrationSettings, build_registration
from gw_imposition.barcodes import BarcodeSettings, build_barcode
from gw_imposition.pdf_export import identity, points
from gw_imposition.finishing import FinishingOperation
from gw_imposition.paper_stocks import PaperStock
from gw_imposition.pdf_service import inspect_pdf
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas
from alpha_build import write_json, digest


def run_smoke(run):
    package = run/'package'/'GW Bleed Alpha'
    exe = package/'GW-Bleed-Alpha.exe'
    samples = package/'samples'
    samples.mkdir(exist_ok=True)
    source = samples/'sample-artwork.pdf'
    canvas = Canvas(str(source), pagesize=(270,162))
    for label in ('ALPHA FRONT','ALPHA BACK'):
        canvas.setFillColorRGB(.1,.35,.65)
        canvas.rect(9,9,252,144,fill=1,stroke=0)
        canvas.setFillColorRGB(1,1,1)
        canvas.drawString(30,90,label)
        canvas.showPage()
    canvas.save()
    checks = []
    with tempfile.TemporaryDirectory(prefix='GW alpha smoke ') as temp:
        cwd = Path(temp)
        # Remove Python environment hints; the executable must carry its runtime.
        env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
        env['PATH'] = str(Path(os.environ['WINDIR'])/'System32')
        def worker(kind, *args, request=None):
            result = subprocess.run([str(exe),'--gw-worker',kind,*map(str,args)],
                input=json.dumps(request) if request else None, capture_output=True, text=True,
                encoding='utf-8', cwd=cwd, env=env, timeout=150,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:
                raise RuntimeError(f'{kind} worker exited {result.returncode}: {result.stderr[-1000:]}')
            return json.loads(result.stdout)
        for page in (0,1):
            data = worker('pdf',source,page)
            assert data['index'] == page and len(data['pages']) == 2, data
            assert base64.b64decode(data['png']).startswith(b'\x89PNG'), data.keys()
        checks.append('Both PDF pages inspect/render through compiled executable with restricted PATH')
        corrupt = cwd/'corrupt.pdf'; corrupt.write_bytes(b'not a pdf')
        writer=PdfWriter(clone_from=source); writer.encrypt('test-secret'); writer.write(cwd/'encrypted.pdf')
        for bad in (cwd/'missing.pdf',corrupt,cwd/'encrypted.pdf'):
            assert 'error' in worker('pdf',bad,0)
        checks.append('Missing, corrupt and encrypted source errors')
        paper=PaperStock('Alpha sample 12 × 18',304800,457200,'.010',Margins(3175,3175,3175,3175),250)
        profile=replace(load_profile(),stocks=(paper.stock(),),press_margins=paper.printing_margins)
        settings=RegistrationSettings(machine_mark_enabled=True,barcode=BarcodeSettings(enabled=True,value='12305'))
        plain_job=Job(88900,50800,3175,6350)
        for finishing in (False,True):
            job=replace(plain_job,finishing=(FinishingOperation('crease',25400),) if finishing else ())
            result=calculate(job,profile)
            candidate=None
            for c in result.candidates:
                marks=build_registration(c,profile,settings).marks
                if len([m for m in marks if m.axis.startswith('machine')]) != 2: continue
                try: build_barcode(c,profile,settings.barcode,marks)
                except ValueError: continue
                candidate=c; break
            assert candidate is not None, 'No suitable barcode sample layout'
            reg=settings if finishing else RegistrationSettings()
            payload={'schema_version':4,'units':'um','job':asdict(job),'profile_snapshot':asdict(profile),
                'calculation':asdict(result),'selected_candidate_index':result.candidates.index(candidate),
                'source_pdf':source.name,'source_page_index':0,'registration':asdict(reg),
                'paper_stock':asdict(paper),'machine_setup':{'thickness_inches':'.010','crease_depth':2,'job_name':'ALPHA','job_number':123}}
            write_json(samples/('finishing-marks-barcode.json' if finishing else 'plain-layout.json'),payload)
            for mode in ('artwork','lines','combined'):
                output=cwd/f'{finishing}-{mode}.pdf'
                request=dict(source=str(source),destination=str(output),signature=identity(source),page=0,
                    mode=mode,job=asdict(job),profile=asdict(profile),candidate=asdict(candidate),registration=asdict(reg))
                data=worker('export',output,request=request)
                assert data.get('ok'),data
                pdf=PdfReader(output); p=pdf.pages[0]
                assert len(pdf.pages)==1
                assert abs(float(p.mediabox.width)-points(candidate.sheet_width_um))<.0001
                assert abs(float(p.cropbox.height)-points(candidate.sheet_height_um))<.0001
                if mode!='lines':
                    assert 'ALPHA FRONT' in p.extract_text(), 'Text was lost/rasterized'
                if finishing:
                    import pypdfium2 as pdfium
                    import zxingcpp
                    with pdfium.PdfDocument(str(output)) as rendered:
                        bitmap=rendered[0].render(scale=3).to_pil()
                        codes=zxingcpp.read_barcodes(bitmap)
                        assert any(c.text=='12305' for c in codes), 'Barcode failed independent decoding'
                        for mark in build_registration(candidate,profile,reg).marks:
                            r=mark.rect
                            pixel=bitmap.getpixel((int(points(r.x_um+r.width_um/2)*3),int(points(r.y_um+r.height_um/2)*3)))
                            assert max(pixel[:3])<40, f'Missing exported registration rectangle: {mark.axis}'
                before=digest(source)
                request['signature']=[str(source),0,0]
                sentinel=cwd/'existing.pdf'; sentinel.write_bytes(b'keep existing destination')
                assert 'error' in worker('export',sentinel,request=request)
                assert sentinel.read_bytes()==b'keep existing destination' and digest(source)==before
        checks.append('All export modes, text/vector retention, stock boxes, finishing, L-mark arms and Code 39 decoding')
        # Invalid staging path must fail without changing the source.
        request['signature']=identity(source)
        assert 'error' in worker('export',cwd/'absent-directory'/'stage.pdf',request=request)
        proc=subprocess.Popen([str(exe),'--gw-worker','export',str(cwd/'cancelled.pdf')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=cwd,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        proc.kill();proc.communicate(timeout=10)
        assert digest(source)==before
        checks.append('Changed-source rejection, invalid destination and terminated worker preserve source')
        workflow = run/'packaged-workflow-results.json'
        result = subprocess.run([str(exe), '--gw-check-workflow', str(source), str(workflow)],
            cwd=cwd, env=env, capture_output=True, timeout=240,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, (workflow.read_text() if workflow.exists() else result.stderr.decode(errors='replace'))
        assert json.loads(workflow.read_text())['status'] == 'passed'
        checks.append('Compiled GUI preview, page switching, calculation, selected alternative, exports and error recovery')
    write_json(run/'packaged-worker-results.json',{'status':'passed','checks':checks,
        'executable_sha256':digest(exe),'clean_windows_acceptance':'pending',
        'limitation':'Developer-host subprocess checks do not prove clean VM behavior or UI console visibility.'})
    print('Packaged worker smoke tests passed.')


if __name__=='__main__':
    run_smoke(Path(sys.argv[1]).resolve())
