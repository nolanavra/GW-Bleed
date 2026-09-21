import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from gw_imposition.storage_io import atomic_json, read_json, fingerprint
from gw_imposition.pdf_backend import read_source
from gw_imposition.desktop_entry import worker_command
from gw_imposition.profiles import profile_from_data, load_profile
from pdf_fixtures import FixtureDocument

class HardeningTests(unittest.TestCase):
    def test_atomic_layout_failure_preserves_old_destination_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'job.json';target.write_text('original')
            with patch('gw_imposition.storage_io.os.replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError): atomic_json(target,{'schema':4})
            self.assertEqual(target.read_text(),'original');self.assertEqual(list(Path(folder).glob('.gw-layout-*')),[])
            atomic_json(target,{'job':'unicode \u00e9'});self.assertEqual(read_json(target),{'job':'unicode \u00e9'})
    def test_bounded_json_and_pdf_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'large';target.write_bytes(b' '*21)
            with self.assertRaisesRegex(ValueError,'size limit'): read_json(target,20)
            with patch('gw_imposition.pdf_backend.MAX_SOURCE_BYTES',20):
                with self.assertRaisesRegex(ValueError,'256 MiB'): read_source(target)
    def test_content_fingerprint_detects_same_length_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'output';self.assertIsNone(fingerprint(target));target.write_bytes(b'one');a=fingerprint(target);target.write_bytes(b'two');self.assertNotEqual(a,fingerprint(target))
    def test_imported_approval_is_not_trusted(self):
        data=asdict(load_profile());data['approval_state']='approved'
        profile=profile_from_data(data);self.assertEqual(profile.approval_state,'unverified');self.assertIn('Imported approval claim',' '.join(profile.setup_notes))
    def test_worker_entry_points_source_and_frozen(self):
        program,args=worker_command('pdf','input.pdf',0);self.assertEqual(program,sys.executable);self.assertEqual(args[0:4],['-m','gw_imposition.desktop_entry','--gw-worker','pdf'])
        with patch.object(sys,'frozen',True,create=True): self.assertEqual(worker_command('export','staging.pdf')[1],['--gw-worker','export','staging.pdf'])
        with self.assertRaises(ValueError): worker_command('unknown')
    def test_real_worker_entry_point_from_clean_cwd(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with FixtureDocument() as doc: doc.new_page(width=270,height=162);doc.save(path)
            entry=Path(__file__).resolve().parents[1]/'desktop.py'
            result=subprocess.run([sys.executable,str(entry),'--gw-worker','pdf',str(path),'0'],cwd=folder,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);payload=json.loads(result.stdout);self.assertNotIn('error',payload);self.assertEqual(payload['pages'][0]['width_points'],270)

    def test_compiled_workers_use_process_image_not_python_prefix(self):
        import gw_imposition.desktop_entry as entry
        with patch.object(entry, '__compiled__', object(), create=True), \
             patch.object(sys, 'executable', 'missing/python.exe'), \
             patch.object(entry, 'running_executable', return_value='relocated/GW-Bleed-Alpha.exe'):
            for kind in ('pdf', 'export'):
                program, arguments = entry.worker_command(kind, 'file.pdf')
                self.assertEqual(program, 'relocated/GW-Bleed-Alpha.exe')
                self.assertEqual(arguments, ['--gw-worker', kind, 'file.pdf'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows process image API')
    def test_windows_process_image_is_existing_executable(self):
        from gw_imposition.desktop_entry import running_executable
        self.assertTrue(Path(running_executable()).is_file())
        # Windows venv launchers delegate to the base interpreter process.
        expected = getattr(sys, '_base_executable', sys.executable)
        self.assertEqual(Path(running_executable()).resolve(), Path(expected).resolve())
    def test_release_readiness_fails_without_external_evidence(self):
        from tools.release_gate import check
        self.assertGreater(len(check({})),6)
