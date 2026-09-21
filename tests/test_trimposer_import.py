from dataclasses import asdict, replace
import unittest
from gw_imposition.models import Job, Margins
from gw_imposition.profiles import load_profile
from gw_imposition.layout_engine import calculate
from gw_imposition.machine_guide import MachineSetup
from gw_imposition.finishing import FinishingOperation
from gw_imposition.trimposer_export import trimposer_ini


class TrimposerImportTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.job = Job(88900,50800,3175,6350)

    def imported(self, candidate, job=None):
        job = job or self.job
        text = trimposer_ini(job,self.profile,candidate,MachineSetup('.008',2,'Sample'),job_number=123).decode('ascii')
        return replace(job, finishing=(), trimposer_ini=text)

    def test_all_alternatives_keep_exact_geometry_and_rotation(self):
        for original in calculate(self.job,self.profile).candidates:
            imported = self.imported(original)
            c = calculate(imported,self.profile).recommended
            self.assertEqual(c.placements,original.placements)
            self.assertEqual(c.bleed_regions,original.bleed_regions)
            self.assertEqual(c.rotation,original.rotation)
            self.assertEqual(c.cuts,original.cuts)
            self.assertEqual(c.slitters,original.slitters)
            self.assertEqual(c,calculate(Job(**asdict(imported)),self.profile).recommended)

    def test_sheet_finishing_and_zero_start_preserved(self):
        job = replace(self.job,finishing=(FinishingOperation('crease',25400),FinishingOperation('strike_perf',20000,0,25400)))
        c = calculate(job,self.profile).recommended
        imported = self.imported(c,job)
        result = calculate(imported,self.profile).recommended
        self.assertEqual(set(c.finishing),set(result.finishing))

    def test_bounds_mismatch_and_unsupported_inputs(self):
        imported = self.imported(calculate(self.job,self.profile).recommended)
        for job in (replace(imported,width_um=90000),replace(imported,bleed_um=10000)):
            with self.assertRaisesRegex(ValueError,'does not fit'):
                calculate(job,self.profile)
        with self.assertRaisesRegex(ValueError,'does not fit'):
            calculate(imported,replace(self.profile,press_margins=Margins(100000,100000,100000,100000)))
        with self.assertRaisesRegex(ValueError,'Unsupported'):
            calculate(replace(imported,trimposer_ini=imported.trimposer_ini.replace('m_Is_Fold_Enable=0','m_Is_Fold_Enable=1')),self.profile)
        with self.assertRaises(ValueError):
            calculate(replace(imported,trimposer_ini=imported.trimposer_ini.replace('m_Paper_Width=', 'm_Paper_Width=NaN')),self.profile)
