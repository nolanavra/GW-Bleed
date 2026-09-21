import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from gw_imposition.machine_manuals import catalog, documents_for, manual_path, machine_context


class ManualTests(unittest.TestCase):
    def test_originals_and_page_references(self):
        from pypdf import PdfReader
        docs = catalog()['documents']
        self.assertEqual(len(docs), 10)
        self.assertEqual(len({d['id'] for d in docs}), 10)
        for doc in docs:
            path = manual_path(doc['id'], verify=True)
            self.assertEqual(len(PdfReader(path).pages), doc['pages'])
            for note in doc['notes']:
                self.assertTrue(all(1 <= p <= doc['pages'] for p in note['pages']))

    def test_unresolved_models_do_not_inherit_other_manual_limits(self):
        self.assertIn('Side trim', machine_context('pt_33sc'))
        self.assertFalse(documents_for('custom'))
        self.assertIn('PDF page(s) 5, 35', machine_context('pt_331scc_air', 'crease'))
        self.assertIn('0.15', machine_context('pt_331scc_air'))

    def test_source_archive_includes_only_catalogued_pdfs(self):
        from tools.source_archive import source_files
        expected = {manual_path(d['id']) for d in catalog()['documents']}
        self.assertEqual({p for p in source_files() if p.suffix == '.pdf'}, expected)

    def test_panel_opens_installed_copy_and_explains_provenance(self):
        from PySide6.QtWidgets import QApplication
        from gw_imposition.machine_panel import MachinePanel
        from gw_imposition.profiles import load_profile, BUNDLED_PROFILES
        app = QApplication.instance() or QApplication([])
        panel = MachinePanel()
        panel.set_profile(load_profile(BUNDLED_PROFILES['pt_331scc_air']))
        self.assertEqual(panel.manuals.count(), 10)
        self.assertIn('MANUAL SOURCES', panel.details.toPlainText())
        self.assertIn('exact cover match', panel.manual_summary.toPlainText())
        with patch('gw_imposition.machine_panel.QDesktopServices.openUrl', return_value=True) as opened:
            panel.open_manual()
            self.assertEqual(Path(opened.call_args.args[0].toLocalFile()), manual_path(panel.manuals.currentData()))
        panel.close()
