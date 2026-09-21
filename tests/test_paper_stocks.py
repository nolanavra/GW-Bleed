import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from dataclasses import asdict,replace
from PySide6.QtWidgets import QApplication
from gw_imposition.paper_stocks import PaperStock, automatic_crease_depth, standard_paper_stocks, stock_fits_machine
from gw_imposition.gui import MainWindow
from gw_imposition.layout_engine import calculate
from gw_imposition.models import Job
from gw_imposition.profiles import load_profile


class PaperStockTests(unittest.TestCase):
    def test_printing_margins_ignore_finisher_bounds_and_roundtrip(self):
        from gw_imposition.models import Margins
        paper = PaperStock('Cover',304800,457200,printing_margins=Margins(3200,4100,5000,6000),gsm=250)
        self.assertEqual(PaperStock(**asdict(paper)),paper)
        profile = replace(load_profile(),stocks=(paper.stock(),),press_margins=paper.printing_margins)
        job = Job(88900,50800,3175,6350)
        baseline = calculate(job,profile).candidates
        expanded = calculate(job,replace(profile,finisher_margins=Margins(50000,50000,80000,80000))).candidates
        self.assertEqual(baseline,expanded)
        for c in baseline:
            self.assertEqual(max(b.y_um+b.height_um for b in c.bleed_regions),c.sheet_height_um-6000)
        self.assertEqual({p.gsm for p in standard_paper_stocks()},{200,250,300})
        self.assertTrue(all(stock_fits_machine(p,load_profile()) for p in standard_paper_stocks()))
        with self.assertRaises(ValueError):
            PaperStock('Bad',304800,457200,printing_margins=Margins(304800,0,0,0))

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_validation_and_dimensions(self):
        paper = PaperStock('Cover',457200,304800,'.012')
        self.assertEqual(PaperStock(**asdict(paper)),paper)
        stock = paper.stock()
        self.assertEqual((stock.width_um,stock.height_um),(304800,457200))
        result = calculate(Job(88900,50800,3175,6350),replace(load_profile(),stocks=(stock,)))
        self.assertTrue(result.candidates)
        self.assertTrue(all(c.stock_id=='Cover' and c.sheet_width_um==304800 for c in result.candidates))
        for thickness in ('0','-1','NaN'):
            with self.assertRaises(ValueError):
                PaperStock('Bad',304800,457200,thickness)

    def test_automatic_depth_endpoints_rounding_and_limits(self):
        cap = replace(load_profile().capabilities,min_paper_thickness_um=127,max_paper_thickness_um=381)
        for thickness, depth in (('.005',1),('.0075',2),('.010',3),('.0125',4),('.015',5),('.00625',2)):
            self.assertEqual(automatic_crease_depth(thickness,cap),depth)
        self.assertEqual(automatic_crease_depth('.010',load_profile().capabilities),2)
        self.assertEqual(automatic_crease_depth('',None),2)
        with self.assertRaises(ValueError):
            automatic_crease_depth('.016',cap)

    def test_dropdown_applies_thickness_and_advanced_visibility(self):
        w = MainWindow()
        paper = PaperStock('Test cover',304800,457200,'.012')
        w.paper_profiles.append(paper)
        w.refresh_paper_profiles()
        self.assertTrue(w.table.isHidden())
        w.advanced_layouts.setChecked(True)
        self.assertFalse(w.table.isHidden())
        w.paper_profile.setCurrentIndex(w.paper_profiles.index(paper)+1)
        self.assertEqual(w.read_machine_setup().thickness_inches,'.012')
        self.assertIn('.012',w.paper_details.text())
        self.assertFalse(w.bleed_logo.pixmap().isNull())
        w.advanced_layouts.setChecked(False)
        w.show()
        self.app.processEvents()
        w.grab().save('build/paper-stock-layout.png')
        w.close()
