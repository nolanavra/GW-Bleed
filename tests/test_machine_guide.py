import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import tempfile
from pathlib import Path
from gw_imposition.storage_io import atomic_json
from gw_imposition.layout_storage import read_layout
from dataclasses import replace, asdict
from gw_imposition.machine_guide import build_guide, MachineSetup, machine_inches
from gw_imposition.models import Job
from gw_imposition.profiles import load_profile, BUNDLED_PROFILES
from gw_imposition.layout_engine import calculate
from gw_imposition.finishing import FinishingMark
from PySide6.QtWidgets import QApplication
from gw_imposition.machine_guide_ui import MachineGuideDialog


class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from PySide6.QtGui import QFontDatabase
        font = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.profile = load_profile(BUNDLED_PROFILES['pt_9375scc_supercut'])
        self.job = Job(88900, 50800, 3175, 6350)
        self.c = calculate(self.job, self.profile).candidates[0]

    def guide(self, **changes):
        return build_guide(self.job, self.profile, replace(self.c, **changes))

    def test_conversion_alternatives_and_rotations(self):
        candidates = calculate(self.job, self.profile).candidates
        self.assertEqual({c.rotation for c in candidates}, {0, 90})
        self.assertGreaterEqual(len({c.stock_id for c in candidates}), 2)
        for c in candidates:
            g = build_guide(self.job, self.profile, c)
            self.assertEqual(g.slits, tuple(sorted(c.sheet_width_um-x for x in c.slitter_x_um)))
            self.assertEqual(g.cuts, tuple(sorted(set(c.cut_y_um))))
            self.assertEqual(g.candidate, c)

    def test_strikes_auto_manual_zero_and_segments(self):
        marks = tuple(FinishingMark('strike_perf', x, a, x, b) for x in (10000, 20000, 30000, 40000) for a,b in ((0, 25400), (25400, 50800)))
        g = self.guide(finishing=marks, finishing_warnings=('greater than 60%: solenoids may burn out.',))
        self.assertEqual([t.automatic for t in g.strikes], [True, True, False, False])
        self.assertEqual(g.strikes[0].right_um, self.c.sheet_width_um-40000)
        self.assertEqual(g.strikes[0].segments, ((0,25400), (25400,50800)))
        self.assertIn('60%', g.warnings[0])
        profile = load_profile(BUNDLED_PROFILES['pt_8336scc_multi'])
        self.assertFalse(any(t.automatic for t in build_guide(self.job, profile, replace(self.c, finishing=marks)).strikes))

    def test_rotary_cross_and_conflicts(self):
        g = self.guide(finishing=(FinishingMark('rotary_perf',10000,0,10000,self.c.sheet_height_um), FinishingMark('cross_perf',0,25400,self.c.sheet_width_um,25400)))
        self.assertEqual(g.strikes, ())
        self.assertEqual(g.creases, (25400,))
        self.assertTrue(g.cross_perf)
        self.assertTrue(any('No program entry' in p for p in g.physical))
        self.assertTrue(self.guide(cut_y_um=(1000,1001)).conflicts)
        self.assertTrue(self.guide(finishing=(FinishingMark('strike_perf',10000,1000,10000,1001),)).conflicts)
        self.assertEqual(machine_inches(Decimal('12.7')), '0.001')

    def test_settings_and_unsupported(self):
        self.assertFalse(MachineSetup().complete)
        setup = MachineSetup('.008', 2, 'Example')
        self.assertEqual(MachineSetup(**asdict(setup)), setup)
        for value in ('NaN', '-1', '0', 'inf'):
            with self.assertRaises(ValueError):
                MachineSetup(value)
        with self.assertRaises(ValueError):
            build_guide(self.job, load_profile(BUNDLED_PROFILES['pt_33sc']), self.c)

    def test_saved_settings_and_legacy(self):
        payload = dict(schema_version=4, units='um', job=asdict(self.job), profile_snapshot=asdict(self.profile),
                       calculation=asdict(calculate(self.job,self.profile)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'job.json'
            for version in (3,4):
                payload['schema_version'] = version
                atomic_json(path,payload)
                self.assertEqual(read_layout(path,include_machine_setup=True)[-1], MachineSetup())
            setup = MachineSetup('.008', 4, 'My job')
            payload['machine_setup'] = asdict(setup)
            atomic_json(path,payload)
            self.assertEqual(read_layout(path,include_machine_setup=True)[-1],setup)
            self.assertEqual(len(read_layout(path)),6)

    def test_dedicated_registration_mark_positions(self):
        from gw_imposition.registration import RegistrationSettings, build_registration
        settings = RegistrationSettings(machine_mark_enabled=True)
        result = build_registration(self.c,self.profile,settings)
        mark = next(m for m in result.marks if m.axis == 'machine')
        positions = (mark.rect.y_um,self.c.sheet_width_um-mark.rect.x_um-mark.rect.width_um)
        d = MachineGuideDialog(self.guide(),MachineSetup('.008',2),registration_position=positions)
        self.assertEqual(d.sheet_values()[4:],list(map(machine_inches,positions)))
        self.assertLessEqual(mark.rect.y_um+mark.rect.height_um,min(p.y_um for p in self.c.bleed_regions))
        self.assertFalse(any(m.axis == 'machine' for m in build_registration(self.c,self.profile,RegistrationSettings()).marks))
        self.assertEqual(RegistrationSettings(**asdict(settings)),settings)
        d.close()

    def test_strike_entry_screen(self):
        marks = tuple(FinishingMark('strike_perf',x,0,x,50800) for x in (10000,20000,30000,40000))
        d = MachineGuideDialog(self.guide(finishing=marks),MachineSetup('.008',2))
        d.show()
        d.show_strikes()
        self.app.processEvents()
        d.grab().save('build/machine-guide-strikes.png')
        d.strike_entry(0)
        self.assertTrue(d.table.item(0,0).text().startswith('Sideways:'))
        self.assertEqual(d.table.item(1,0).text(),'Start: 0.000')
        d.show_strikes()
        d.strike_entry(2)
        self.assertEqual(d.table.item(0,0).text(),'Start: 0.000')
        d.close()

    def test_main_window_selection_and_preview_independence(self):
        from gw_imposition.gui import MainWindow
        w = MainWindow()
        w.job, w.profile = self.job,self.profile
        w.calculation_finished(w.revision,calculate(self.job,self.profile),'')
        self.assertTrue(w.guide_button.isEnabled())
        w.open_machine_guide()
        self.assertTrue(w.guide.valid)
        self.assertIs(w.layout_views.currentWidget(), w.guide)
        self.assertFalse(w.guide.isWindow())
        self.assertTrue(w.guide.setup_inputs.isHidden())
        self.assertFalse(w.back_to_layout.isHidden())
        w.back_to_layout.click()
        self.assertEqual(w.layout_views.currentIndex(),0)
        self.assertTrue(w.back_to_layout.isHidden())
        from gw_imposition.paper_stocks import PaperStock
        paper = PaperStock('Guide test',304800,457200,'.010')
        w.paper_profiles.append(paper)
        w.refresh_paper_profiles(paper)
        w.setup_job_name.setText('Header test')
        self.assertFalse(w.guide.valid)
        w.open_machine_guide()
        self.assertEqual(w.guide.sheet_values()[2],'0.010')
        self.assertEqual(w.read_machine_setup().crease_depth,2)
        self.assertNotIn('Machine setup',[w.results_tabs.tabText(i) for i in range(w.results_tabs.count())])
        w.show()
        self.app.processEvents()
        w.grab().save('build/machine-guide-embedded.png')
        w.apply_theme('Light')
        self.assertTrue(w.guide.valid)
        w.table.selectRow(1)
        self.assertFalse(w.guide.valid)
        w.open_machine_guide()
        self.assertEqual(w.guide.data.candidate,w.result.candidates[1])
        w.invalidate()
        self.assertFalse(w.guide.valid)
        self.assertFalse(w.guide_button.isEnabled())
        w.close()

    def test_trimposer_save_dialog_writes_ini(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QLineEdit,QDialogButtonBox
        from gw_imposition.gui import MainWindow
        from gw_imposition.paper_stocks import PaperStock
        w=MainWindow()
        w.registration_panel.barcode_enabled.setChecked(False)
        profile=replace(w.current_machine_profile(),capabilities=replace(w.current_machine_profile().capabilities,min_paper_thickness_um=127,max_paper_thickness_um=381))
        w.loaded_profiles[w.machine.currentData()]=profile
        paper=PaperStock('Exchange',304800,457200,'.008')
        w.paper_profiles.append(paper)
        w.refresh_paper_profiles(paper)
        w.setup_job_number.setText('321')
        w.job,w.profile=self.job,profile
        w.calculation_finished(w.revision,calculate(self.job,profile),'')
        self.assertTrue(w.trimposer_button.isEnabled())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'MachineParameterFile_321.ini'
            def execute(dialog):
                self.assertEqual(dialog.findChildren(QLineEdit),[])
                dialog.findChild(QDialogButtonBox).accepted.emit()
                return 1
            with patch('gw_imposition.gui.QDialog.exec',execute),patch('gw_imposition.gui.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                w.choose_trimposer_save()
            self.assertIn(b'm_JobNO=321',path.read_bytes())
            self.assertIn(b'm_ProcessSpeed_Grade=4',path.read_bytes())
            self.assertIn(b'm_Crease_Level=2',path.read_bytes())
        w.close()

    def test_dialog_navigation_and_invalidation(self):
        d = MachineGuideDialog(self.guide(), MachineSetup('.008', 2))
        d.show()
        self.app.processEvents()
        self.assertTrue(d.confirm.isEnabled())
        self.assertEqual(d.screen_title.text(),'Program parameters')
        self.assertFalse(d.left_rail.isHidden())
        self.assertFalse(d.right_rail.isHidden())
        d.strike_next.click()
        self.assertEqual(d.table.columnCount(),4)
        self.assertEqual(d.table.item(0,0).text(),'0.000 (unused)')
        d.categories['Crease'].click()
        self.assertEqual(d.table.rowCount(),16)
        self.assertIn('unused',d.table.item(0,0).text())
        d.show_main()
        self.assertEqual(d.table.horizontalHeaderItem(1).text(),'Cuts')
        self.assertEqual(d.table.item(0,1).text(),machine_inches(d.data.cuts[0]))
        self.assertEqual(d.table.horizontalHeaderItem(2).text(),'Slitters')
        d.category('Sheet')
        self.assertEqual(d.table.rowCount(),6)
        d.acknowledge()
        self.assertEqual(d.completed, {0})
        d.move_step(1)
        self.assertEqual(d.table.item(0,0).text(), machine_inches(d.data.slits[0]))
        d.resize(1300,900)
        self.app.processEvents()
        self.assertEqual(d.overlay.geometry(), d.rect())
        d.grab().save('build/machine-guide-screen.png')
        d.show_main()
        self.app.processEvents()
        d.grab().save('build/machine-guide-overview.png')
        d.steps.setCurrentRow(len(d.data.steps)-1)
        self.app.processEvents()
        self.assertTrue(d.category_bar.isHidden())
        self.assertTrue(all(not b.isHidden() for b in d.layout_buttons.values()))
        d.layout_buttons['Low speed'].click()
        self.assertEqual(d.layout_buttons['Low speed'].text(),'High speed')
        d.grab().save('build/machine-guide-review.png')
        d.invalidate()
        self.assertFalse(d.confirm.isEnabled())
        self.assertFalse(d.completed)
        d.close()

from decimal import Decimal
